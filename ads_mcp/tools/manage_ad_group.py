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

"""Tool for creating, updating, and removing Google Ads ad groups."""

from typing import Any, Dict

from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.coordinator import mcp


def _create_ad_group(
    customer_id: str,
    campaign_id: str | None,
    name: str | None,
    status: str | None,
    cpc_bid_micros: int | None,
) -> Dict[str, Any]:
    if not campaign_id:
        raise ToolError("'campaign_id' is required for create.")
    if not name:
        raise ToolError("'name' is required for create.")

    client = utils.get_googleads_client()
    ad_group_service = utils.get_googleads_service("AdGroupService")
    ad_group_op = utils.get_googleads_type("AdGroupOperation")
    ad_group = ad_group_op.create
    ad_group.name = name
    ad_group.campaign = f"customers/{customer_id}/campaigns/{campaign_id}"
    ad_group.status = getattr(
        client.enums.AdGroupStatusEnum, status or "PAUSED"
    )

    if cpc_bid_micros is not None:
        ad_group.cpc_bid_micros = cpc_bid_micros

    response = ad_group_service.mutate_ad_groups(
        customer_id=customer_id, operations=[ad_group_op]
    )

    return {"resource_name": response.results[0].resource_name}


def _update_ad_group(
    customer_id: str,
    ad_group_id: str | None,
    name: str | None,
    status: str | None,
    cpc_bid_micros: int | None,
) -> Dict[str, Any]:
    if not ad_group_id:
        raise ToolError("'ad_group_id' is required for update.")
    if name is None and status is None and cpc_bid_micros is None:
        raise ToolError(
            "At least one of 'name', 'status', or 'cpc_bid_micros' "
            "is required for update."
        )

    client = utils.get_googleads_client()
    ad_group_rn = f"customers/{customer_id}/adGroups/{ad_group_id}"
    ad_group_service = utils.get_googleads_service("AdGroupService")
    ad_group_op = utils.get_googleads_type("AdGroupOperation")
    ad_group = ad_group_op.update
    ad_group.resource_name = ad_group_rn

    update_paths = []
    if name is not None:
        ad_group.name = name
        update_paths.append("name")
    if status is not None:
        ad_group.status = getattr(client.enums.AdGroupStatusEnum, status)
        update_paths.append("status")
    if cpc_bid_micros is not None:
        ad_group.cpc_bid_micros = cpc_bid_micros
        update_paths.append("cpc_bid_micros")

    ad_group_op.update_mask.paths.extend(update_paths)
    ad_group_service.mutate_ad_groups(
        customer_id=customer_id, operations=[ad_group_op]
    )

    return {"resource_name": ad_group_rn, "updated": update_paths}


def _remove_ad_group(
    customer_id: str, ad_group_id: str | None
) -> Dict[str, Any]:
    if not ad_group_id:
        raise ToolError("'ad_group_id' is required for remove.")

    ad_group_rn = f"customers/{customer_id}/adGroups/{ad_group_id}"
    current_status = utils.get_resource_status(
        customer_id, ad_group_rn, "ad_group.status", "ad_group"
    )

    if current_status == "ENABLED":
        raise ToolError(
            f"Cannot remove ad group '{ad_group_id}' with status ENABLED. "
            "Pause it first: operation='update', status='PAUSED'."
        )

    ad_group_service = utils.get_googleads_service("AdGroupService")
    ad_group_op = utils.get_googleads_type("AdGroupOperation")
    ad_group_op.remove = ad_group_rn
    response = ad_group_service.mutate_ad_groups(
        customer_id=customer_id, operations=[ad_group_op]
    )

    return {"resource_name": response.results[0].resource_name, "removed": True}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def manage_ad_group(
    customer_id: str,
    operation: str,
    ad_group_id: str | None = None,
    campaign_id: str | None = None,
    name: str | None = None,
    status: str | None = None,
    cpc_bid_micros: int | None = None,
) -> Dict[str, Any]:
    """Creates, updates, or removes a Google Ads ad group.

    Args:
        customer_id: Customer ID (digits only, no hyphens;
            e.g. 123-456-7890 becomes 1234567890).
        operation: 'create', 'update', or 'remove'.
        ad_group_id: Ad group ID. Required for 'update' and 'remove'.
        campaign_id: Campaign ID. Required for 'create'.
        name: Ad group name. Required for 'create'.
        status: Ad group status. One of: ENABLED, PAUSED.
            Defaults to PAUSED on 'create'.
        cpc_bid_micros: Default CPC bid in micros (1,000,000 = $1).

    Returns:
        dict with resource_name of the ad group.

    Notes:
        - 'remove' is blocked if the ad group status is ENABLED.
          Pause it first: operation='update', status='PAUSED'.
    """
    op = operation.lower()

    if op not in ("create", "update", "remove"):
        raise ToolError(
            f"Invalid operation '{operation}'. "
            "Must be 'create', 'update', or 'remove'."
        )

    try:
        if op == "create":
            return _create_ad_group(
                customer_id, campaign_id, name, status, cpc_bid_micros
            )
        elif op == "update":
            return _update_ad_group(
                customer_id, ad_group_id, name, status, cpc_bid_micros
            )
        else:
            return _remove_ad_group(customer_id, ad_group_id)
    except GoogleAdsException as ex:
        utils.raise_for_google_ads_exception(ex)
