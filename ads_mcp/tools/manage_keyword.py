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

"""Tool for creating, updating, and removing Google Ads keywords."""

from typing import Any, Dict

from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.coordinator import mcp

_SUPPORTED_MATCH_TYPES = ("EXACT", "PHRASE", "BROAD")


def _create_keyword(
    customer_id: str,
    ad_group_id: str | None,
    text: str | None,
    match_type: str | None,
    status: str | None,
    cpc_bid_micros: int | None,
) -> Dict[str, Any]:
    if not ad_group_id:
        raise ToolError("'ad_group_id' is required for create.")
    if not text:
        raise ToolError("'text' is required for create.")
    if not match_type:
        raise ToolError("'match_type' is required for create.")

    match_type_upper = match_type.upper()
    if match_type_upper not in _SUPPORTED_MATCH_TYPES:
        raise ToolError(
            f"Invalid match_type '{match_type}'. "
            f"Supported: {', '.join(_SUPPORTED_MATCH_TYPES)}."
        )

    client = utils.get_googleads_client()
    criterion_service = utils.get_googleads_service("AdGroupCriterionService")
    criterion_op = utils.get_googleads_type("AdGroupCriterionOperation")
    criterion = criterion_op.create
    criterion.ad_group = f"customers/{customer_id}/adGroups/{ad_group_id}"
    criterion.status = getattr(
        client.enums.AdGroupCriterionStatusEnum, status or "PAUSED"
    )
    criterion.keyword.text = text
    criterion.keyword.match_type = getattr(
        client.enums.KeywordMatchTypeEnum, match_type_upper
    )

    if cpc_bid_micros is not None:
        criterion.cpc_bid_micros = cpc_bid_micros

    response = criterion_service.mutate_ad_group_criteria(
        customer_id=customer_id, operations=[criterion_op]
    )

    return {"resource_name": response.results[0].resource_name}


def _update_keyword(
    customer_id: str,
    ad_group_id: str | None,
    criterion_id: str | None,
    status: str | None,
    cpc_bid_micros: int | None,
) -> Dict[str, Any]:
    if not ad_group_id:
        raise ToolError("'ad_group_id' is required for update.")
    if not criterion_id:
        raise ToolError("'criterion_id' is required for update.")
    if status is None and cpc_bid_micros is None:
        raise ToolError(
            "At least one of 'status' or 'cpc_bid_micros' is required for "
            "update. Keyword text and match type cannot be changed after "
            "creation."
        )

    client = utils.get_googleads_client()
    criterion_rn = (
        f"customers/{customer_id}/adGroupCriteria"
        f"/{ad_group_id}~{criterion_id}"
    )
    criterion_service = utils.get_googleads_service("AdGroupCriterionService")
    criterion_op = utils.get_googleads_type("AdGroupCriterionOperation")
    criterion = criterion_op.update
    criterion.resource_name = criterion_rn

    update_paths = []
    if status is not None:
        criterion.status = getattr(
            client.enums.AdGroupCriterionStatusEnum, status
        )
        update_paths.append("status")
    if cpc_bid_micros is not None:
        criterion.cpc_bid_micros = cpc_bid_micros
        update_paths.append("cpc_bid_micros")

    criterion_op.update_mask.paths.extend(update_paths)
    criterion_service.mutate_ad_group_criteria(
        customer_id=customer_id, operations=[criterion_op]
    )

    return {"resource_name": criterion_rn, "updated": update_paths}


def _remove_keyword(
    customer_id: str,
    ad_group_id: str | None,
    criterion_id: str | None,
) -> Dict[str, Any]:
    if not ad_group_id:
        raise ToolError("'ad_group_id' is required for remove.")
    if not criterion_id:
        raise ToolError("'criterion_id' is required for remove.")

    criterion_rn = (
        f"customers/{customer_id}/adGroupCriteria"
        f"/{ad_group_id}~{criterion_id}"
    )
    current_status = utils.get_resource_status(
        customer_id,
        criterion_rn,
        "ad_group_criterion.status",
        "ad_group_criterion",
    )

    if current_status == "ENABLED":
        raise ToolError(
            f"Cannot remove keyword '{criterion_id}' with status ENABLED. "
            "Pause it first: operation='update', status='PAUSED'."
        )

    criterion_service = utils.get_googleads_service("AdGroupCriterionService")
    criterion_op = utils.get_googleads_type("AdGroupCriterionOperation")
    criterion_op.remove = criterion_rn
    response = criterion_service.mutate_ad_group_criteria(
        customer_id=customer_id, operations=[criterion_op]
    )

    return {"resource_name": response.results[0].resource_name, "removed": True}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def manage_keyword(
    customer_id: str,
    operation: str,
    ad_group_id: str | None = None,
    criterion_id: str | None = None,
    text: str | None = None,
    match_type: str | None = None,
    status: str | None = None,
    cpc_bid_micros: int | None = None,
) -> Dict[str, Any]:
    """Creates, updates, or removes a Google Ads keyword.

    Args:
        customer_id: Customer ID (digits only, no hyphens;
            e.g. 123-456-7890 becomes 1234567890).
        operation: 'create', 'update', or 'remove'.
        ad_group_id: Ad group ID. Required for all operations.
        criterion_id: Keyword criterion ID. Required for 'update' and 'remove'.
        text: Keyword text. Required for 'create'.
        match_type: Keyword match type. Required for 'create'.
            One of: EXACT, PHRASE, BROAD.
        status: Keyword status. One of: ENABLED, PAUSED.
            Defaults to PAUSED on 'create'.
        cpc_bid_micros: CPC bid in micros (1,000,000 = $1).

    Returns:
        dict with resource_name of the keyword criterion.

    Notes:
        - Keyword text and match type cannot be changed after creation.
          Remove and recreate to change them.
        - 'remove' is blocked if the keyword status is ENABLED.
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
            return _create_keyword(
                customer_id,
                ad_group_id,
                text,
                match_type,
                status,
                cpc_bid_micros,
            )
        elif op == "update":
            return _update_keyword(
                customer_id, ad_group_id, criterion_id, status, cpc_bid_micros
            )
        else:
            return _remove_keyword(customer_id, ad_group_id, criterion_id)
    except GoogleAdsException as ex:
        utils.raise_for_google_ads_exception(ex)
