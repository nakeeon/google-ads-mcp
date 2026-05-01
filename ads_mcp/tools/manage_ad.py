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

"""Tool for creating, updating, and removing Google Ads ads (AdGroupAds)."""

from typing import Any, Dict, List

from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.coordinator import mcp


def _create_ad(
    customer_id: str,
    ad_group_id: str | None,
    headlines: List[str] | None,
    descriptions: List[str] | None,
    final_urls: List[str] | None,
    status: str | None,
) -> Dict[str, Any]:
    if not ad_group_id:
        raise ToolError("'ad_group_id' is required for create.")
    if not headlines or len(headlines) < 3:
        raise ToolError(
            "'headlines' is required for create and must have at least 3 items."
        )
    if not descriptions or len(descriptions) < 2:
        raise ToolError(
            "'descriptions' is required for create and must have at least "
            "2 items."
        )
    if not final_urls:
        raise ToolError("'final_urls' is required for create.")

    client = utils.get_googleads_client()
    ad_group_ad_service = utils.get_googleads_service("AdGroupAdService")
    ad_group_ad_op = utils.get_googleads_type("AdGroupAdOperation")
    ad_group_ad = ad_group_ad_op.create
    ad_group_ad.ad_group = f"customers/{customer_id}/adGroups/{ad_group_id}"
    ad_group_ad.status = getattr(
        client.enums.AdGroupAdStatusEnum, status or "PAUSED"
    )

    for url in final_urls:
        ad_group_ad.ad.final_urls.append(url)

    for text in headlines:
        asset = client.get_type("AdTextAsset")
        asset.text = text
        ad_group_ad.ad.responsive_search_ad.headlines.append(asset)

    for text in descriptions:
        asset = client.get_type("AdTextAsset")
        asset.text = text
        ad_group_ad.ad.responsive_search_ad.descriptions.append(asset)

    response = ad_group_ad_service.mutate_ad_group_ads(
        customer_id=customer_id, operations=[ad_group_ad_op]
    )

    return {"resource_name": response.results[0].resource_name}


def _update_ad(
    customer_id: str,
    ad_group_id: str | None,
    ad_id: str | None,
    status: str | None,
) -> Dict[str, Any]:
    if not ad_group_id:
        raise ToolError("'ad_group_id' is required for update.")
    if not ad_id:
        raise ToolError("'ad_id' is required for update.")
    if status is None:
        raise ToolError(
            "Only 'status' can be updated on an existing ad. "
            "To change ad content, remove the ad and create a new one."
        )

    client = utils.get_googleads_client()
    ad_group_ad_rn = f"customers/{customer_id}/adGroupAds/{ad_group_id}~{ad_id}"
    ad_group_ad_service = utils.get_googleads_service("AdGroupAdService")
    ad_group_ad_op = utils.get_googleads_type("AdGroupAdOperation")
    ad_group_ad = ad_group_ad_op.update
    ad_group_ad.resource_name = ad_group_ad_rn
    ad_group_ad.status = getattr(client.enums.AdGroupAdStatusEnum, status)
    ad_group_ad_op.update_mask.paths.extend(["status"])
    ad_group_ad_service.mutate_ad_group_ads(
        customer_id=customer_id, operations=[ad_group_ad_op]
    )

    return {"resource_name": ad_group_ad_rn, "updated": ["status"]}


def _remove_ad(
    customer_id: str,
    ad_group_id: str | None,
    ad_id: str | None,
) -> Dict[str, Any]:
    if not ad_group_id:
        raise ToolError("'ad_group_id' is required for remove.")
    if not ad_id:
        raise ToolError("'ad_id' is required for remove.")

    ad_group_ad_rn = f"customers/{customer_id}/adGroupAds/{ad_group_id}~{ad_id}"
    current_status = utils.get_resource_status(
        customer_id, ad_group_ad_rn, "ad_group_ad.status", "ad_group_ad"
    )

    if current_status == "ENABLED":
        raise ToolError(
            f"Cannot remove ad '{ad_id}' with status ENABLED. "
            "Pause it first: operation='update', status='PAUSED'."
        )

    ad_group_ad_service = utils.get_googleads_service("AdGroupAdService")
    ad_group_ad_op = utils.get_googleads_type("AdGroupAdOperation")
    ad_group_ad_op.remove = ad_group_ad_rn
    response = ad_group_ad_service.mutate_ad_group_ads(
        customer_id=customer_id, operations=[ad_group_ad_op]
    )

    return {"resource_name": response.results[0].resource_name, "removed": True}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def manage_ad(
    customer_id: str,
    operation: str,
    ad_group_id: str | None = None,
    ad_id: str | None = None,
    headlines: List[str] | None = None,
    descriptions: List[str] | None = None,
    final_urls: List[str] | None = None,
    status: str | None = None,
) -> Dict[str, Any]:
    """Creates, updates, or removes a Google Ads Responsive Search Ad.

    Args:
        customer_id: Customer ID (digits only, no hyphens;
            e.g. 123-456-7890 becomes 1234567890).
        operation: 'create', 'update', or 'remove'.
        ad_group_id: Ad group ID. Required for all operations.
        ad_id: Ad ID. Required for 'update' and 'remove'.
        headlines: List of headline strings (3–15 items). Required for 'create'.
            Each headline must be 30 characters or fewer.
        descriptions: List of description strings (2–4 items).
            Required for 'create'. Each description must be 90 characters
            or fewer.
        final_urls: List of landing page URLs. Required for 'create'.
        status: Ad status. One of: ENABLED, PAUSED.
            Defaults to PAUSED on 'create'.

    Returns:
        dict with resource_name of the ad group ad.

    Notes:
        - Only 'status' can be changed on 'update'. To change ad content
          (headlines, descriptions, or URLs), remove the ad and create a
          new one.
        - 'remove' is blocked if the ad status is ENABLED.
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
            return _create_ad(
                customer_id,
                ad_group_id,
                headlines,
                descriptions,
                final_urls,
                status,
            )
        elif op == "update":
            return _update_ad(customer_id, ad_group_id, ad_id, status)
        else:
            return _remove_ad(customer_id, ad_group_id, ad_id)
    except GoogleAdsException as ex:
        utils.raise_for_google_ads_exception(ex)
