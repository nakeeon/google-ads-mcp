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

"""Test cases for the manage_ad tool."""

import unittest
from unittest.mock import MagicMock, patch

from fastmcp.exceptions import ToolError

from ads_mcp.tools.manage_ad import manage_ad
from tests.tools.helpers import make_mutate_response

_HEADLINES = ["Headline 1", "Headline 2", "Headline 3"]
_DESCRIPTIONS = ["Description 1", "Description 2"]
_FINAL_URLS = ["https://www.example.com"]


class TestManageAd(unittest.TestCase):
    """Test cases for the manage_ad tool."""

    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_client")
    def test_create_rsa(self, mock_client, mock_get_type, mock_get_service):
        """Tests that create builds a responsive search ad."""
        mock_client.return_value = MagicMock()

        # get_type is called once for the operation + once per headline/description
        ad_group_ad_op = MagicMock()
        asset_mock = MagicMock()
        mock_get_type.side_effect = [ad_group_ad_op] + [asset_mock] * (
            len(_HEADLINES) + len(_DESCRIPTIONS)
        )

        ad_service = MagicMock()
        mock_get_service.return_value = ad_service
        expected_rn = "customers/123/adGroupAds/456~789"
        ad_service.mutate_ad_group_ads.return_value = make_mutate_response(
            expected_rn
        )

        result = manage_ad(
            customer_id="123",
            operation="create",
            ad_group_id="456",
            headlines=_HEADLINES,
            descriptions=_DESCRIPTIONS,
            final_urls=_FINAL_URLS,
        )

        self.assertEqual(result["resource_name"], expected_rn)
        ad_service.mutate_ad_group_ads.assert_called_once()

    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_client")
    def test_update_ad_status(
        self, mock_client, mock_get_type, mock_get_service
    ):
        """Tests that update sets status on the AdGroupAd."""
        mock_client.return_value = MagicMock()

        ad_group_ad_op = MagicMock()
        mock_get_type.return_value = ad_group_ad_op

        ad_service = MagicMock()
        mock_get_service.return_value = ad_service
        ad_service.mutate_ad_group_ads.return_value = make_mutate_response(
            "customers/123/adGroupAds/456~789"
        )

        result = manage_ad(
            customer_id="123",
            operation="update",
            ad_group_id="456",
            ad_id="789",
            status="PAUSED",
        )

        self.assertIn("status", result["updated"])
        ad_group_ad_op.update_mask.paths.extend.assert_called_once_with(
            ["status"]
        )

    @patch("ads_mcp.utils.get_resource_status")
    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    def test_remove_blocked_when_enabled(
        self, mock_get_type, mock_get_service, mock_status
    ):
        """Tests that remove raises ToolError when ad is ENABLED."""
        mock_status.return_value = "ENABLED"

        with self.assertRaises(ToolError) as ctx:
            manage_ad(
                customer_id="123",
                operation="remove",
                ad_group_id="456",
                ad_id="789",
            )

        self.assertIn("ENABLED", str(ctx.exception))
        mock_get_service.assert_not_called()

    @patch("ads_mcp.utils.get_resource_status")
    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    def test_remove_succeeds_when_paused(
        self, mock_get_type, mock_get_service, mock_status
    ):
        """Tests that remove proceeds when ad is PAUSED."""
        mock_status.return_value = "PAUSED"

        ad_group_ad_op = MagicMock()
        mock_get_type.return_value = ad_group_ad_op

        ad_service = MagicMock()
        mock_get_service.return_value = ad_service
        ad_service.mutate_ad_group_ads.return_value = make_mutate_response(
            "customers/123/adGroupAds/456~789"
        )

        result = manage_ad(
            customer_id="123",
            operation="remove",
            ad_group_id="456",
            ad_id="789",
        )

        self.assertTrue(result["removed"])
        ad_service.mutate_ad_group_ads.assert_called_once()

    def test_create_missing_ad_group_id_raises(self):
        """Tests that create without ad_group_id raises ToolError."""
        with self.assertRaises(ToolError) as ctx:
            manage_ad(
                customer_id="123",
                operation="create",
                headlines=_HEADLINES,
                descriptions=_DESCRIPTIONS,
                final_urls=_FINAL_URLS,
            )
        self.assertIn("'ad_group_id' is required", str(ctx.exception))

    def test_create_too_few_headlines_raises(self):
        """Tests that create with fewer than 3 headlines raises ToolError."""
        with self.assertRaises(ToolError) as ctx:
            manage_ad(
                customer_id="123",
                operation="create",
                ad_group_id="456",
                headlines=["H1", "H2"],
                descriptions=_DESCRIPTIONS,
                final_urls=_FINAL_URLS,
            )
        self.assertIn("at least 3", str(ctx.exception))

    def test_create_too_few_descriptions_raises(self):
        """Tests that create with fewer than 2 descriptions raises ToolError."""
        with self.assertRaises(ToolError) as ctx:
            manage_ad(
                customer_id="123",
                operation="create",
                ad_group_id="456",
                headlines=_HEADLINES,
                descriptions=["D1"],
                final_urls=_FINAL_URLS,
            )
        self.assertIn("at least", str(ctx.exception))

    def test_update_content_not_supported_raises(self):
        """Tests that updating ad content raises an informative ToolError."""
        with self.assertRaises(ToolError) as ctx:
            manage_ad(
                customer_id="123",
                operation="update",
                ad_group_id="456",
                ad_id="789",
            )
        self.assertIn("Only 'status' can be updated", str(ctx.exception))

    def test_invalid_operation_raises(self):
        """Tests that an invalid operation raises ToolError."""
        with self.assertRaises(ToolError) as ctx:
            manage_ad(customer_id="123", operation="delete")
        self.assertIn("Invalid operation", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
