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

"""Test cases for the manage_campaign tool."""

import unittest
from unittest.mock import MagicMock, patch

from fastmcp.exceptions import ToolError

from ads_mcp.tools.manage_campaign import manage_campaign
from tests.tools.helpers import make_mutate_response


class TestManageCampaign(unittest.TestCase):
    """Test cases for the manage_campaign tool."""

    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_client")
    def test_create_campaign(
        self, mock_client, mock_get_type, mock_get_service
    ):
        """Tests that create builds a budget then a campaign."""
        mock_client.return_value = MagicMock()

        budget_op = MagicMock()
        campaign_op = MagicMock()
        mock_get_type.side_effect = [budget_op, campaign_op]

        budget_service = MagicMock()
        campaign_service = MagicMock()
        mock_get_service.side_effect = [budget_service, campaign_service]

        budget_service.mutate_campaign_budgets.return_value = (
            make_mutate_response("customers/123/campaignBudgets/456")
        )
        campaign_service.mutate_campaigns.return_value = make_mutate_response(
            "customers/123/campaigns/789"
        )

        result = manage_campaign(
            customer_id="123",
            operation="create",
            name="Test Campaign",
            budget_amount_micros=5_000_000,
            advertising_channel_type="SEARCH",
        )

        self.assertEqual(result["resource_name"], "customers/123/campaigns/789")
        budget_service.mutate_campaign_budgets.assert_called_once()
        campaign_service.mutate_campaigns.assert_called_once()

    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_client")
    def test_update_campaign_name(
        self, mock_client, mock_get_type, mock_get_service
    ):
        """Tests that update sets name and update_mask correctly."""
        mock_client.return_value = MagicMock()

        campaign_op = MagicMock()
        mock_get_type.return_value = campaign_op

        campaign_service = MagicMock()
        mock_get_service.return_value = campaign_service
        campaign_service.mutate_campaigns.return_value = make_mutate_response(
            "customers/123/campaigns/789"
        )

        result = manage_campaign(
            customer_id="123",
            operation="update",
            campaign_id="789",
            name="New Name",
        )

        self.assertEqual(result["resource_name"], "customers/123/campaigns/789")
        self.assertIn("name", result["updated"])
        campaign_op.update_mask.paths.extend.assert_called_once_with(["name"])

    @patch("ads_mcp.utils.get_resource_status")
    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    def test_remove_blocked_when_enabled(
        self, mock_get_type, mock_get_service, mock_status
    ):
        """Tests that remove raises ToolError when campaign is ENABLED."""
        mock_status.return_value = "ENABLED"

        with self.assertRaises(ToolError) as ctx:
            manage_campaign(
                customer_id="123",
                operation="remove",
                campaign_id="789",
            )

        self.assertIn("ENABLED", str(ctx.exception))
        mock_get_service.assert_not_called()

    @patch("ads_mcp.utils.get_resource_status")
    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    def test_remove_succeeds_when_paused(
        self, mock_get_type, mock_get_service, mock_status
    ):
        """Tests that remove proceeds when campaign is PAUSED."""
        mock_status.return_value = "PAUSED"

        campaign_op = MagicMock()
        mock_get_type.return_value = campaign_op

        campaign_service = MagicMock()
        mock_get_service.return_value = campaign_service
        campaign_service.mutate_campaigns.return_value = make_mutate_response(
            "customers/123/campaigns/789"
        )

        result = manage_campaign(
            customer_id="123",
            operation="remove",
            campaign_id="789",
        )

        self.assertTrue(result["removed"])
        campaign_service.mutate_campaigns.assert_called_once()

    def test_create_missing_name_raises(self):
        """Tests that create without name raises ToolError."""
        with self.assertRaises(ToolError) as ctx:
            manage_campaign(
                customer_id="123",
                operation="create",
                advertising_channel_type="SEARCH",
            )
        self.assertIn("'name' is required", str(ctx.exception))

    def test_create_missing_channel_type_raises(self):
        """Tests that create without advertising_channel_type raises ToolError."""
        with self.assertRaises(ToolError) as ctx:
            manage_campaign(
                customer_id="123",
                operation="create",
                name="Test",
            )
        self.assertIn(
            "'advertising_channel_type' is required", str(ctx.exception)
        )

    def test_update_missing_campaign_id_raises(self):
        """Tests that update without campaign_id raises ToolError."""
        with self.assertRaises(ToolError) as ctx:
            manage_campaign(
                customer_id="123",
                operation="update",
                name="New Name",
            )
        self.assertIn("'campaign_id' is required", str(ctx.exception))

    def test_invalid_operation_raises(self):
        """Tests that an invalid operation raises ToolError."""
        with self.assertRaises(ToolError) as ctx:
            manage_campaign(
                customer_id="123",
                operation="delete",
            )
        self.assertIn("Invalid operation", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
