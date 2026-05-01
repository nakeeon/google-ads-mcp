# Copyright 2026 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tool for creating, updating, and removing Google Ads campaigns."""

from typing import Any, Dict

from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from mcp.types import ToolAnnotations


import ads_mcp.utils as utils
from ads_mcp.coordinator import mcp

_SUPPORTED_BIDDING_STRATEGIES = (
    "MANUAL_CPC",
    "TARGET_CPA",
    "TARGET_ROAS",
    "MAXIMIZE_CONVERSIONS",
    "MAXIMIZE_CONVERSION_VALUE",
    "TARGET_SPEND",
)


def _apply_bidding_strategy(campaign, strategy: str, client) -> None:
    if strategy == "MANUAL_CPC":
        campaign.manual_cpc = client.get_type("ManualCpc")
    elif strategy == "TARGET_CPA":
        campaign.target_cpa.target_cpa_micros = 1_000_000
    elif strategy == "TARGET_ROAS":
        campaign.target_roas.target_roas = 2.0
    elif strategy == "MAXIMIZE_CONVERSIONS":
        campaign.maximize_conversions.target_cpa_micros = 0
    elif strategy == "MAXIMIZE_CONVERSION_VALUE":
        campaign.maximize_conversion_value.target_roas = 0
    elif strategy == "TARGET_SPEND":
        campaign.target_spend.target_spend_micros = 0
    else:
        raise ToolError(
            f"Unsupported bidding_strategy_type '{strategy}'. "
            f"Supported: {', '.join(_SUPPORTED_BIDDING_STRATEGIES)}."
        )


def _create_campaign(
    customer_id: str,
    name: str | None,
    budget_amount_micros: int | None,
    advertising_channel_type: str | None,
    status: str | None,
    bidding_strategy_type: str | None,
) -> Dict[str, Any]:
    if not name:
        raise ToolError("'name' is required for create.")
    if not advertising_channel_type:
        raise ToolError("'advertising_channel_type' is required for create.")

    client = utils.get_googleads_client()

    budget_service = utils.get_googleads_service("CampaignBudgetService")
    budget_op = utils.get_googleads_type("CampaignBudgetOperation")
    budget_op.create.amount_micros = budget_amount_micros or 1_000_000
    budget_op.create.delivery_method = (
        client.enums.BudgetDeliveryMethodEnum.STANDARD
    )
    budget_response = budget_service.mutate_campaign_budgets(
        customer_id=customer_id, operations=[budget_op]
    )
    budget_rn = budget_response.results[0].resource_name

    campaign_service = utils.get_googleads_service("CampaignService")
    campaign_op = utils.get_googleads_type("CampaignOperation")
    campaign = campaign_op.create
    campaign.name = name
    campaign.campaign_budget = budget_rn
    campaign.advertising_channel_type = getattr(
        client.enums.AdvertisingChannelTypeEnum, advertising_channel_type
    )
    campaign.status = getattr(
        client.enums.CampaignStatusEnum, status or "PAUSED"
    )

    _apply_bidding_strategy(
        campaign, (bidding_strategy_type or "MANUAL_CPC").upper(), client
    )

    response = campaign_service.mutate_campaigns(
        customer_id=customer_id, operations=[campaign_op]
    )

    return {"resource_name": response.results[0].resource_name}


def _update_campaign_budget(
    customer_id: str, campaign_rn: str, budget_amount_micros: int
) -> None:
    ga_service = utils.get_googleads_service("GoogleAdsService")
    query = (
        f"SELECT campaign.campaign_budget FROM campaign "
        f"WHERE campaign.resource_name = '{campaign_rn}'"
    )
    budget_rn = None
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            budget_rn = row.campaign.campaign_budget
            break

    if not budget_rn:
        raise ToolError(f"Could not find budget for campaign '{campaign_rn}'.")

    budget_service = utils.get_googleads_service("CampaignBudgetService")
    budget_op = utils.get_googleads_type("CampaignBudgetOperation")
    budget_op.update.resource_name = budget_rn
    budget_op.update.amount_micros = budget_amount_micros
    budget_op.update_mask.paths.extend(["amount_micros"])
    budget_service.mutate_campaign_budgets(
        customer_id=customer_id, operations=[budget_op]
    )


def _update_campaign(
    customer_id: str,
    campaign_id: str | None,
    name: str | None,
    status: str | None,
    budget_amount_micros: int | None,
) -> Dict[str, Any]:
    if not campaign_id:
        raise ToolError("'campaign_id' is required for update.")
    if name is None and status is None and budget_amount_micros is None:
        raise ToolError(
            "At least one of 'name', 'status', or 'budget_amount_micros' "
            "is required for update."
        )

    campaign_rn = f"customers/{customer_id}/campaigns/{campaign_id}"
    updated = []

    if budget_amount_micros is not None:
        _update_campaign_budget(customer_id, campaign_rn, budget_amount_micros)
        updated.append("budget")

    update_paths = []
    if name is not None:
        update_paths.append("name")
    if status is not None:
        update_paths.append("status")

    if update_paths:
        client = utils.get_googleads_client()
        campaign_service = utils.get_googleads_service("CampaignService")
        campaign_op = utils.get_googleads_type("CampaignOperation")
        campaign = campaign_op.update
        campaign.resource_name = campaign_rn

        if name is not None:
            campaign.name = name
        if status is not None:
            campaign.status = getattr(client.enums.CampaignStatusEnum, status)

        campaign_op.update_mask.paths.extend(update_paths)
        campaign_service.mutate_campaigns(
            customer_id=customer_id, operations=[campaign_op]
        )
        updated.extend(update_paths)

    return {"resource_name": campaign_rn, "updated": updated}


def _remove_campaign(
    customer_id: str, campaign_id: str | None
) -> Dict[str, Any]:
    if not campaign_id:
        raise ToolError("'campaign_id' is required for remove.")

    campaign_rn = f"customers/{customer_id}/campaigns/{campaign_id}"
    current_status = utils.get_resource_status(
        customer_id, campaign_rn, "campaign.status", "campaign"
    )

    if current_status == "ENABLED":
        raise ToolError(
            f"Cannot remove campaign '{campaign_id}' with status ENABLED. "
            "Pause it first: operation='update', status='PAUSED'."
        )

    campaign_service = utils.get_googleads_service("CampaignService")
    campaign_op = utils.get_googleads_type("CampaignOperation")
    campaign_op.remove = campaign_rn
    response = campaign_service.mutate_campaigns(
        customer_id=customer_id, operations=[campaign_op]
    )

    return {"resource_name": response.results[0].resource_name, "removed": True}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def manage_campaign(
    customer_id: str,
    operation: str,
    campaign_id: str | None = None,
    name: str | None = None,
    budget_amount_micros: int | None = None,
    advertising_channel_type: str | None = None,
    status: str | None = None,
    bidding_strategy_type: str | None = None,
) -> Dict[str, Any]:
    """Creates, updates, or removes a Google Ads campaign.

    Args:
        customer_id: Customer ID (digits only, no hyphens;
            e.g. 123-456-7890 becomes 1234567890).
        operation: 'create', 'update', or 'remove'.
        campaign_id: Campaign ID. Required for 'update' and 'remove'.
        name: Campaign name. Required for 'create'.
        budget_amount_micros: Daily budget in micros (1,000,000 = $1/day).
            Required for 'create'. On 'update', updates the existing budget.
        advertising_channel_type: Channel type. Required for 'create'.
            One of: SEARCH, DISPLAY, SHOPPING, VIDEO, PERFORMANCE_MAX.
        status: Campaign status. One of: ENABLED, PAUSED.
            Defaults to PAUSED on 'create'.
        bidding_strategy_type: Bidding strategy. Used on 'create' only.
            One of: MANUAL_CPC, TARGET_CPA, TARGET_ROAS,
            MAXIMIZE_CONVERSIONS, MAXIMIZE_CONVERSION_VALUE, TARGET_SPEND.
            Defaults to MANUAL_CPC.

    Returns:
        dict with resource_name of the campaign.

    Notes:
        - New campaigns default to PAUSED to prevent immediate ad serving.
        - 'remove' is blocked if the campaign status is ENABLED.
          Pause it first, then remove.
        - Bidding strategy cannot be changed after creation.
    """
    op = operation.lower()

    if op not in ("create", "update", "remove"):
        raise ToolError(
            f"Invalid operation '{operation}'. "
            "Must be 'create', 'update', or 'remove'."
        )

    try:
        if op == "create":
            return _create_campaign(
                customer_id,
                name,
                budget_amount_micros,
                advertising_channel_type,
                status,
                bidding_strategy_type,
            )
        elif op == "update":
            return _update_campaign(
                customer_id,
                campaign_id,
                name,
                status,
                budget_amount_micros,
            )
        else:
            return _remove_campaign(customer_id, campaign_id)
    except GoogleAdsException as ex:
        utils.raise_for_google_ads_exception(ex)
