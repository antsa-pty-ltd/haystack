"""
Policy Violation Logging Integration Tests (Improved)

Simplified version using test helpers for better readability and maintainability.
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

import pytest
import asyncio
from unittest.mock import patch, AsyncMock

from tests.helpers import (
    MockPolicyResponseBuilder,
    MockNestJSAPIBuilder,
    TestDataFactory
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class TestPolicyViolationLoggingImproved:
    """Simplified tests for policy violation logging"""

    async def test_violation_logged_with_correct_structure(self, async_client):
        """
        Test that policy violations are logged with correct data structure.

        This is a simplified version that focuses on the data structure.
        """
        logged_violations = []
        logging_completed = asyncio.Event()

        # Create test data using factory
        request_data = TestDataFactory.create_document_request(
            template=TestDataFactory.create_violating_template(),
            client_info=TestDataFactory.create_client_info(id="client_123", name="John Doe"),
            practitioner_info=TestDataFactory.create_practitioner_info(id="prac_123")
        )

        # Create mocks using builders
        policy_response = MockPolicyResponseBuilder() \
            .with_violation(
                violation_type="medical_diagnosis_request",
                reason="Template requests DSM-5 diagnosis",
                confidence="high"
            ) \
            .build()

        with patch('main.openai_client') as mock_openai, \
             patch('httpx.AsyncClient') as mock_http_client:

            mock_openai.chat.completions.create = AsyncMock(return_value=policy_response)

            # Track violations
            async def capture_violation(url, **kwargs):
                if '/admin/policy-violations' in url:
                    logged_violations.append(kwargs.get('json', {}))
                    logging_completed.set()

                from unittest.mock import AsyncMock
                response = AsyncMock()
                response.status_code = 201
                response.json.return_value = {"success": True}
                return response

            mock_client = MockNestJSAPIBuilder() \
                .add_endpoint('/admin/policy-violations', {"success": True}, 201) \
                .build()
            mock_client.post.side_effect = capture_violation
            mock_http_client.return_value = mock_client

            # Make request
            response = await async_client.post(
                "/generate-document-from-template",
                json=request_data,
                headers=TestDataFactory.create_headers(profile_id="profile_123")
            )

            # Verify response
            assert response.status_code == 200
            assert "POLICY VIOLATION" in response.json()["content"].upper()

            # Wait for logging
            try:
                await asyncio.wait_for(logging_completed.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                pytest.fail("Logging timeout")

            # Verify violation structure
            assert len(logged_violations) > 0, "Should log violation"
            violation = logged_violations[0]

            # Check camelCase fields
            assert violation["profileId"] == "profile_123"
            assert violation["templateId"] == "violating_template_1"
            assert violation["violationType"] == "medical_diagnosis_request"
            assert violation["clientId"] == "client_123"

    async def test_multiple_violations_logged_separately_simplified(self, async_client):
        """
        Simplified test for multiple violations.
        """
        logged_violations = []
        expected_count = 3
        logging_completed = asyncio.Event()

        # Create 3 different violating templates
        templates = [
            TestDataFactory.create_violating_template(id=f"tmpl_{i}", name=f"Template {i}")
            for i in range(1, 4)
        ]

        policy_response = MockPolicyResponseBuilder() \
            .with_violation() \
            .build()

        with patch('main.openai_client') as mock_openai, \
             patch('httpx.AsyncClient') as mock_http_client:

            mock_openai.chat.completions.create = AsyncMock(return_value=policy_response)

            async def capture_violations(url, **kwargs):
                if '/admin/policy-violations' in url:
                    logged_violations.append(kwargs.get('json', {}))
                    if len(logged_violations) >= expected_count:
                        logging_completed.set()

                from unittest.mock import AsyncMock
                response = AsyncMock()
                response.status_code = 201
                response.json.return_value = {"success": True}
                return response

            mock_client = MockNestJSAPIBuilder().build()
            mock_client.post.side_effect = capture_violations
            mock_http_client.return_value = mock_client

            # Send 3 requests
            for template in templates:
                request = TestDataFactory.create_document_request(template=template)
                await async_client.post(
                    "/generate-document-from-template",
                    json=request,
                    headers=TestDataFactory.create_headers()
                )

            # Wait for all logging
            try:
                await asyncio.wait_for(logging_completed.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pytest.fail(f"Expected {expected_count} logs, got {len(logged_violations)}")

            # Verify
            assert len(logged_violations) == expected_count
            template_ids = [v["templateId"] for v in logged_violations]
            assert len(set(template_ids)) == expected_count, "Should have unique template IDs"

    async def test_logging_failure_non_blocking(self, async_client):
        """
        Test that logging failures don't block user response.
        """
        request_data = TestDataFactory.create_document_request(
            template=TestDataFactory.create_violating_template()
        )

        policy_response = MockPolicyResponseBuilder() \
            .with_violation() \
            .build()

        with patch('main.openai_client') as mock_openai, \
             patch('httpx.AsyncClient') as mock_http_client:

            mock_openai.chat.completions.create = AsyncMock(return_value=policy_response)

            # Mock API returns 500 error
            mock_client = MockNestJSAPIBuilder() \
                .add_endpoint('/admin/policy-violations', {"error": "Server error"}, 500) \
                .build()
            mock_http_client.return_value = mock_client

            # Request should still succeed
            response = await async_client.post(
                "/generate-document-from-template",
                json=request_data,
                headers=TestDataFactory.create_headers()
            )

            # User gets warning despite logging failure
            assert response.status_code == 200, "Should not block user"
            assert "POLICY VIOLATION" in response.json()["content"].upper()

            # Give async task time to fail
            await asyncio.sleep(0.5)
