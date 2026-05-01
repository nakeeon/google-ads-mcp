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

"""Test cases for the manage_keyword tool."""

import unittest
from unittest.mock import MagicMock, patch

from fastmcp.exceptions import ToolError

from ads_mcp.tools.manage_keyword import manage_keyword
from tests.tools.helpers import make_mutate_response


class TestManageKeyword(unittest.TestCase):
    """Test cases for the manage_keyword tool."""

    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_client")
    def test_create_keyword(self, mock_client, mock_get_type, mock_get_service):
        """Tests that create builds and submits a keyword operation."""
        mock_client.return_value = MagicMock()

        criterion_op = MagicMock()
        mock_get_type.return_value = criterion_op

        criterion_service = MagicMock()
        mock_get_service.return_value = criterion_service
        expected_rn = "customers/123/adGroupCriteria/456~789"
        criterion_service.mutate_ad_group_criteria.return_value = (
            make_mutate_response(expected_rn)
        )

        result = manage_keyword(
            customer_id="123",
            operation="create",
            ad_group_id="456",
            text="running shoes",
            match_type="EXACT",
        )

        self.assertEqual(result["resource_name"], expected_rn)
        criterion_service.mutate_ad_group_criteria.assert_called_once()

    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_client")
    def test_update_keyword_bid(
        self, mock_client, mock_get_type, mock_get_service
    ):
        """Tests that update sets cpc_bid_micros and update_mask correctly."""
        mock_client.return_value = MagicMock()

        criterion_op = MagicMock()
        mock_get_type.return_value = criterion_op

        criterion_service = MagicMock()
        mock_get_service.return_value = criterion_service
        criterion_service.mutate_ad_group_criteria.return_value = (
            make_mutate_response("customers/123/adGroupCriteria/456~789")
        )

        result = manage_keyword(
            customer_id="123",
            operation="update",
            ad_group_id="456",
            criterion_id="789",
            cpc_bid_micros=2_000_000,
        )

        self.assertIn("cpc_bid_micros", result["updated"])
        criterion_op.update_mask.paths.extend.assert_called_once_with(
            ["cpc_bid_micros"]
        )

    @patch("ads_mcp.utils.get_resource_status")
    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    def test_remove_blocked_when_enabled(
        self, mock_get_type, mock_get_service, mock_status
    ):
        """Tests that remove raises ToolError when keyword is ENABLED."""
        mock_status.return_value = "ENABLED"

        with self.assertRaises(ToolError) as ctx:
            manage_keyword(
                customer_id="123",
                operation="remove",
                ad_group_id="456",
                criterion_id="789",
            )

        self.assertIn("ENABLED", str(ctx.exception))
        mock_get_service.assert_not_called()

    @patch("ads_mcp.utils.get_resource_status")
    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    def test_remove_succeeds_when_paused(
        self, mock_get_type, mock_get_service, mock_status
    ):
        """Tests that remove proceeds when keyword is PAUSED."""
        mock_status.return_value = "PAUSED"

        criterion_op = MagicMock()
        mock_get_type.return_value = criterion_op

        criterion_service = MagicMock()
        mock_get_service.return_value = criterion_service
        criterion_service.mutate_ad_group_criteria.return_value = (
            make_mutate_response("customers/123/adGroupCriteria/456~789")
        )

        result = manage_keyword(
            customer_id="123",
            operation="remove",
            ad_group_id="456",
            criterion_id="789",
        )

        self.assertTrue(result["removed"])
        criterion_service.mutate_ad_group_criteria.assert_called_once()

    def test_create_missing_text_raises(self):
        """Tests that create without text raises ToolError."""
        with self.assertRaises(ToolError) as ctx:
            manage_keyword(
                customer_id="123",
                operation="create",
                ad_group_id="456",
                match_type="EXACT",
            )
        self.assertIn("'text' is required", str(ctx.exception))

    def test_create_missing_match_type_raises(self):
        """Tests that create without match_type raises ToolError."""
        with self.assertRaises(ToolError) as ctx:
            manage_keyword(
                customer_id="123",
                operation="create",
                ad_group_id="456",
                text="running shoes",
            )
        self.assertIn("'match_type' is required", str(ctx.exception))

    def test_create_invalid_match_type_raises(self):
        """Tests that create with an invalid match_type raises ToolError."""
        with self.assertRaises(ToolError) as ctx:
            manage_keyword(
                customer_id="123",
                operation="create",
                ad_group_id="456",
                text="running shoes",
                match_type="FUZZY",
            )
        self.assertIn("Invalid match_type", str(ctx.exception))

    def test_update_no_fields_raises(self):
        """Tests that update with no updatable fields raises ToolError."""
        with self.assertRaises(ToolError) as ctx:
            manage_keyword(
                customer_id="123",
                operation="update",
                ad_group_id="456",
                criterion_id="789",
            )
        self.assertIn("At least one of", str(ctx.exception))

    def test_invalid_operation_raises(self):
        """Tests that an invalid operation raises ToolError."""
        with self.assertRaises(ToolError) as ctx:
            manage_keyword(customer_id="123", operation="delete")
        self.assertIn("Invalid operation", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
