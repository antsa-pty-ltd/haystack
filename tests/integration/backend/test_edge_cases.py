"""
Edge Case Tests

Tests for edge cases including Unicode handling, large payloads, and security.
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

import pytest
from unittest.mock import patch

from tests.helpers import (
    MockPolicyResponseBuilder,
    TestDataFactory
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class TestUnicodeHandling:
    """Tests for Unicode character handling"""

    async def test_unicode_client_names(self, async_client):
        """
        Test that system handles various Unicode characters in client names.
        """
        unicode_data = TestDataFactory.create_unicode_test_data()

        for name in unicode_data["names"]:
            # Create request with Unicode name
            request = TestDataFactory.create_document_request(
                template=TestDataFactory.create_safe_template(),
                client_info=TestDataFactory.create_client_info(name=name)
            )

            # Mock policy check to pass
            policy_response = MockPolicyResponseBuilder() \
                .without_violation() \
                .build()

            with patch('main.openai_client') as mock_openai:
                # Mock both policy check and document generation
                mock_openai.chat.completions.create.return_value = policy_response

                response = await async_client.post(
                    "/generate-document-from-template",
                    json=request,
                    headers=TestDataFactory.create_headers()
                )

                # Should handle gracefully (200 or 400, but not 500)
                assert response.status_code in [200, 400], \
                    f"Should handle Unicode name '{name}' gracefully"

    async def test_unicode_in_template_content(self, async_client):
        """
        Test that templates with Unicode characters are processed correctly.
        """
        unicode_templates = [
            "Résumé de la session",
            "患者进展报告",
            "Zusammenfassung der Sitzung",
            "Отчет о прогрессе"
        ]

        for content in unicode_templates:
            template = TestDataFactory.create_template(content=content)
            request = TestDataFactory.create_document_request(template=template)

            policy_response = MockPolicyResponseBuilder() \
                .without_violation() \
                .build()

            with patch('main.openai_client') as mock_openai:
                mock_openai.chat.completions.create.return_value = policy_response

                response = await async_client.post(
                    "/generate-document-from-template",
                    json=request,
                    headers=TestDataFactory.create_headers()
                )

                assert response.status_code in [200, 400], \
                    f"Should handle Unicode content: {content[:30]}"

    async def test_emoji_in_messages(self, async_client):
        """
        Test that emoji in client names are handled properly.
        """
        emoji_name = "Test Client 💡 Emoji"

        request = TestDataFactory.create_document_request(
            client_info=TestDataFactory.create_client_info(name=emoji_name)
        )

        policy_response = MockPolicyResponseBuilder() \
            .without_violation() \
            .build()

        with patch('main.openai_client') as mock_openai:
            mock_openai.chat.completions.create.return_value = policy_response

            response = await async_client.post(
                "/generate-document-from-template",
                json=request,
                headers=TestDataFactory.create_headers()
            )

            assert response.status_code in [200, 400], \
                "Should handle emoji in names"


class TestLargePayloads:
    """Tests for handling large payloads"""

    async def test_large_transcript_handling(self, async_client):
        """
        Test document generation with large transcript (100 segments).
        """
        large_transcript = TestDataFactory.create_large_transcript(segment_count=100)

        request = TestDataFactory.create_document_request(
            transcript=large_transcript
        )

        policy_response = MockPolicyResponseBuilder() \
            .without_violation() \
            .build()

        with patch('main.openai_client') as mock_openai:
            mock_openai.chat.completions.create.return_value = policy_response

            response = await async_client.post(
                "/generate-document-from-template",
                json=request,
                headers=TestDataFactory.create_headers()
            )

            # Should either succeed or return 413 (Payload Too Large)
            assert response.status_code in [200, 413], \
                f"Should handle large payload, got {response.status_code}"

    async def test_very_long_template_content(self, async_client):
        """
        Test template with very long content.
        """
        # Create template with ~10KB content
        long_content = "This is a very long template. " * 300  # ~9KB

        request = TestDataFactory.create_document_request(
            template=TestDataFactory.create_template(content=long_content)
        )

        policy_response = MockPolicyResponseBuilder() \
            .without_violation() \
            .build()

        with patch('main.openai_client') as mock_openai:
            mock_openai.chat.completions.create.return_value = policy_response

            response = await async_client.post(
                "/generate-document-from-template",
                json=request,
                headers=TestDataFactory.create_headers()
            )

            assert response.status_code in [200, 413], \
                "Should handle long template content"

    async def test_many_transcript_segments(self, async_client):
        """
        Test transcript with many segments (stress test).
        """
        large_transcript = TestDataFactory.create_large_transcript(segment_count=500)

        request = TestDataFactory.create_document_request(
            transcript=large_transcript
        )

        policy_response = MockPolicyResponseBuilder() \
            .without_violation() \
            .build()

        with patch('main.openai_client') as mock_openai:
            mock_openai.chat.completions.create.return_value = policy_response

            response = await async_client.post(
                "/generate-document-from-template",
                json=request,
                headers=TestDataFactory.create_headers(),
                timeout=30.0  # Allow more time for large payload
            )

            # Should handle or reject gracefully
            assert response.status_code in [200, 413, 504], \
                "Should handle or reject large transcript gracefully"


class TestSecurityEdgeCases:
    """Tests for security-related edge cases"""

    async def test_special_characters_in_names(self, async_client):
        """
        Test that special characters in names don't cause issues.
        """
        special_names = [
            "O'Brien",  # Apostrophe
            "Test <script>alert('xss')</script>",  # XSS attempt
            "Test'; DROP TABLE clients;--",  # SQL injection attempt
            "Test\nNewline",  # Newline
            "Test\tTab",  # Tab
            'Test "quotes"',  # Double quotes
            "Test & Ampersand",  # Ampersand
        ]

        for name in special_names:
            request = TestDataFactory.create_document_request(
                client_info=TestDataFactory.create_client_info(name=name)
            )

            policy_response = MockPolicyResponseBuilder() \
                .without_violation() \
                .build()

            with patch('main.openai_client') as mock_openai:
                mock_openai.chat.completions.create.return_value = policy_response

                response = await async_client.post(
                    "/generate-document-from-template",
                    json=request,
                    headers=TestDataFactory.create_headers()
                )

                # Should handle safely (not 500)
                assert response.status_code != 500, \
                    f"Should handle special chars safely: {name}"

    async def test_empty_string_fields(self, async_client):
        """
        Test handling of empty string fields.
        """
        request = TestDataFactory.create_document_request(
            client_info=TestDataFactory.create_client_info(name=""),
            practitioner_info=TestDataFactory.create_practitioner_info(name="")
        )

        policy_response = MockPolicyResponseBuilder() \
            .without_violation() \
            .build()

        with patch('main.openai_client') as mock_openai:
            mock_openai.chat.completions.create.return_value = policy_response

            response = await async_client.post(
                "/generate-document-from-template",
                json=request,
                headers=TestDataFactory.create_headers()
            )

            # Should validate or handle gracefully
            assert response.status_code in [200, 400, 422], \
                "Should handle empty strings"

    async def test_null_fields_in_request(self, async_client):
        """
        Test handling of null/None fields.
        """
        request = {
            "template": TestDataFactory.create_safe_template(),
            "transcript": TestDataFactory.create_transcript(),
            "clientInfo": None,  # Null client info
            "practitionerInfo": TestDataFactory.create_practitioner_info(),
            "generationInstructions": None
        }

        policy_response = MockPolicyResponseBuilder() \
            .without_violation() \
            .build()

        with patch('main.openai_client') as mock_openai:
            mock_openai.chat.completions.create.return_value = policy_response

            response = await async_client.post(
                "/generate-document-from-template",
                json=request,
                headers=TestDataFactory.create_headers()
            )

            # Should validate properly
            assert response.status_code in [200, 400, 422], \
                "Should handle null fields"

    async def test_missing_required_fields(self, async_client):
        """
        Test handling when required fields are missing.
        """
        # Request missing template
        incomplete_request = {
            "transcript": TestDataFactory.create_transcript(),
            "clientInfo": TestDataFactory.create_client_info(),
            "practitionerInfo": TestDataFactory.create_practitioner_info()
        }

        response = await async_client.post(
            "/generate-document-from-template",
            json=incomplete_request,
            headers=TestDataFactory.create_headers()
        )

        # Should return validation error
        assert response.status_code in [400, 422], \
            "Should return validation error for missing fields"


class TestConcurrencyEdgeCases:
    """Tests for concurrency edge cases"""

    async def test_concurrent_document_generation_same_client(self, async_client):
        """
        Test multiple concurrent document generations for same client.
        """
        import asyncio

        request = TestDataFactory.create_document_request(
            client_info=TestDataFactory.create_client_info(id="client_concurrent")
        )

        policy_response = MockPolicyResponseBuilder() \
            .without_violation() \
            .build()

        with patch('main.openai_client') as mock_openai:
            mock_openai.chat.completions.create.return_value = policy_response

            # Send 5 concurrent requests
            tasks = []
            for _ in range(5):
                task = async_client.post(
                    "/generate-document-from-template",
                    json=request,
                    headers=TestDataFactory.create_headers()
                )
                tasks.append(task)

            responses = await asyncio.gather(*tasks)

            # All should complete
            assert len(responses) == 5, "All requests should complete"

            # All should succeed (or consistently fail)
            status_codes = [r.status_code for r in responses]
            assert all(code in [200, 400, 422] for code in status_codes), \
                "All requests should handle properly"

    async def test_session_expiry_during_request(self):
        """
        Test handling when session expires during processing.

        This is a placeholder for a more complex test that would require
        timing coordination with Redis TTL.
        """
        # TODO: Implement with proper timing coordination
        pytest.skip("Requires Redis TTL coordination - implement in future")
