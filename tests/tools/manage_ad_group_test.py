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

"""Test cases for the manage_ad_group tool."""

import unittest
from unittest.mock import MagicMock, patch

from fastmcp.exceptions import ToolError

from ads_mcp.tools.manage_ad_group import manage_ad_group
from tests.tools.helpers import make_mutate_response


class TestManageAdGroup(unittest.TestCase):
    """Test cases for the manage_ad_group tool."""

    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_client")
    def test_create_ad_group(
        self, mock_client, mock_get_type, mock_get_service
    ):
        """Tests that create builds and submits an ad group operation."""
        mock_client.return_value = MagicMock()

        ad_group_op = MagicMock()
        mock_get_type.return_value = ad_group_op

        ad_group_service = MagicMock()
        mock_get_service.return_value = ad_group_service
        ad_group_service.mutate_ad_groups.return_value = make_mutate_response(
            "customers/123/adGroups/456"
        )

        result = manage_ad_group(
            customer_id="123",
            operation="create",
            campaign_id="789",
            name="Test Ad Group",
        )

        self.assertEqual(result["resource_name"], "customers/123/adGroups/456")
        ad_group_service.mutate_ad_groups.assert_called_once()

    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_client")
    def test_update_ad_group_status(
        self, mock_client, mock_get_type, mock_get_service
    ):
        """Tests that update sets status and update_mask correctly."""
        mock_client.return_value = MagicMock()

        ad_group_op = MagicMock()
        mock_get_type.return_value = ad_group_op

        ad_group_service = MagicMock()
        mock_get_service.return_value = ad_group_service
        ad_group_service.mutate_ad_groups.return_value = make_mutate_response(
            "customers/123/adGroups/456"
        )

        result = manage_ad_group(
            customer_id="123",
            operation="update",
            ad_group_id="456",
            status="PAUSED",
        )

        self.assertIn("status", result["updated"])
        ad_group_op.update_mask.paths.extend.assert_called_once_with(["status"])

    @patch("ads_mcp.utils.get_resource_status")
    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    def test_remove_blocked_when_enabled(
        self, mock_get_type, mock_get_service, mock_status
    ):
        """Tests that remove raises ToolError when ad group is ENABLED."""
        mock_status.return_value = "ENABLED"

        with self.assertRaises(ToolError) as ctx:
            manage_ad_group(
                customer_id="123",
                operation="remove",
                ad_group_id="456",
            )

        self.assertIn("ENABLED", str(ctx.exception))
        mock_get_service.assert_not_called()

    @patch("ads_mcp.utils.get_resource_status")
    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    def test_remove_succeeds_when_paused(
        self, mock_get_type, mock_get_service, mock_status
    ):
        """Tests that remove proceeds when ad group is PAUSED."""
        mock_status.return_value = "PAUSED"

        ad_group_op = MagicMock()
        mock_get_type.return_value = ad_group_op

        ad_group_service = MagicMock()
        mock_get_service.return_value = ad_group_service
        ad_group_service.mutate_ad_groups.return_value = make_mutate_response(
            "customers/123/adGroups/456"
        )

        result = manage_ad_group(
            customer_id="123",
            operation="remove",
            ad_group_id="456",
        )

        self.assertTrue(result["removed"])
        ad_group_service.mutate_ad_groups.assert_called_once()

    def test_create_missing_campaign_id_raises(self):
        """Tests that create without campaign_id raises ToolError."""
        with self.assertRaises(ToolError) as ctx:
            manage_ad_group(
                customer_id="123",
                operation="create",
                name="Test",
            )
        self.assertIn("'campaign_id' is required", str(ctx.exception))

    def test_create_missing_name_raises(self):
        """Tests that create without name raises ToolError."""
        with self.assertRaises(ToolError) as ctx:
            manage_ad_group(
                customer_id="123",
                operation="create",
                campaign_id="789",
            )
        self.assertIn("'name' is required", str(ctx.exception))

    def test_update_no_fields_raises(self):
        """Tests that update with no fields raises ToolError."""
        with self.assertRaises(ToolError) as ctx:
            manage_ad_group(
                customer_id="123",
                operation="update",
                ad_group_id="456",
            )
        self.assertIn("At least one of", str(ctx.exception))

    def test_invalid_operation_raises(self):
        """Tests that an invalid operation raises ToolError."""
        with self.assertRaises(ToolError) as ctx:
            manage_ad_group(
                customer_id="123",
                operation="delete",
            )
        self.assertIn("Invalid operation", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
