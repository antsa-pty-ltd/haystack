"""
Document Generation End-to-End Tests

Tests successful document generation workflows:
- Happy path generation (template + transcript → document)
- Template variable substitution ({{clientName}}, {{date}}, {{practitionerName}})
- Document refinement workflow (generate → modify → regenerate)
- Concurrent generation for different clients
- Edge cases (empty transcript, very long transcript)
- Generation timeout handling

Integration Points:
- FastAPI ↔ OpenAI (document generation)
- Template processing and variable substitution
- Transcript formatting and processing
- Error handling and resilience

Note: Policy violation tests are in test_policy_violation_logging.py
This file focuses on successful generation scenarios.
"""

import os
import sys
# Add haystack directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timezone
from typing import Dict, Any

# Import test helpers
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from helpers.test_data_factory import TestDataFactory

# Mark all tests as integration tests
pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class TestDocumentGenerationHappyPath:
    """Tests for successful document generation scenarios"""

    async def test_basic_document_generation(self, async_client):
        """
        Test the basic happy path for document generation.

        Flow:
        1. Send template + transcript + client/practitioner info
        2. OpenAI generates document content
        3. Response contains generated document with metadata
        4. No policy violations

        This tests:
        - Basic generation flow
        - Request/response structure
        - OpenAI integration
        - Successful completion
        """
        # Create test data using factory
        request_data = TestDataFactory.create_document_request(
            template=TestDataFactory.create_safe_template(
                id="progress_note_1",
                name="Session Progress Note"
            ),
            transcript=TestDataFactory.create_transcript(segment_count=10),
            client_info=TestDataFactory.create_client_info(
                name="Sarah Johnson",
                id="client_001"
            ),
            practitioner_info=TestDataFactory.create_practitioner_info(
                name="Dr. Emily Chen",
                id="prac_001"
            )
        )

        # Mock successful OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = """# Session Progress Note

**Client:** Sarah Johnson
**Practitioner:** Dr. Emily Chen
**Date:** January 15, 2025

## Session Summary

Sarah Johnson attended today's session and discussed her progress with anxiety management techniques. Dr. Emily Chen reviewed the homework assignments from the previous session and introduced new coping strategies.

## Interventions Used

Dr. Emily Chen utilized Cognitive Behavioral Therapy (CBT) techniques to help Sarah identify and challenge negative thought patterns. Mindfulness exercises were practiced during the session.

## Treatment Plan

Continue with weekly sessions. Sarah agreed to practice daily mindfulness meditation for 10 minutes and track her anxiety levels in a journal.

## Next Steps

Follow-up scheduled for next week to review progress with the new interventions."""

        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = Mock()
        mock_response.usage.total_tokens = 450

        with patch('main.openai_client') as mock_openai:
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

            # Make request
            response = await async_client.post(
                "/generate-document-from-template",
                json=request_data,
                headers=TestDataFactory.create_headers()
            )

            # Verify successful response
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"

            response_data = response.json()
            assert "content" in response_data, "Response should contain 'content' field"
            assert "generatedAt" in response_data, "Response should contain 'generatedAt' timestamp"
            assert "metadata" in response_data, "Response should contain 'metadata' field"

            # Verify content is not empty
            content = response_data["content"]
            assert len(content) > 100, "Generated content should be substantial"

            # Verify names are in the document
            assert "Sarah Johnson" in content, "Document should contain client name"
            assert "Dr. Emily Chen" in content, "Document should contain practitioner name"

            # Verify no policy violation
            metadata = response_data["metadata"]
            assert metadata.get("policyViolation") != True, "Should not be a policy violation"

            # Verify OpenAI was called with correct parameters
            assert mock_openai.chat.completions.create.called
            call_args = mock_openai.chat.completions.create.call_args
            assert call_args[1]["model"] == "gpt-4o"
            assert call_args[1]["temperature"] == 0.8

    async def test_empty_transcript_handling(self, async_client):
        """
        Test document generation with an empty transcript.

        Flow:
        1. Send request with empty transcript (no segments)
        2. OpenAI generates document noting lack of session data
        3. Response successful with appropriate content

        This tests:
        - Empty transcript handling
        - Graceful degradation
        - Error-free processing
        """
        request_data = TestDataFactory.create_document_request(
            template=TestDataFactory.create_safe_template(),
            transcript={"segments": []},  # Empty transcript
            client_info=TestDataFactory.create_client_info(name="Empty Case"),
            practitioner_info=TestDataFactory.create_practitioner_info()
        )

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = """# Progress Note

**Note:** No session transcript available. Unable to document specific discussion points or interventions at this time."""
        mock_response.choices[0].finish_reason = "stop"

        with patch('main.openai_client') as mock_openai:
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

            response = await async_client.post(
                "/generate-document-from-template",
                json=request_data,
                headers=TestDataFactory.create_headers()
            )

            assert response.status_code == 200
            response_data = response.json()

            # Should still generate content, even if minimal
            assert "content" in response_data
            assert len(response_data["content"]) > 0

    async def test_very_long_transcript_handling(self, async_client):
        """
        Test document generation with a very long transcript (100+ segments).

        Flow:
        1. Send request with 150-segment transcript
        2. OpenAI processes large input successfully
        3. Response contains comprehensive document

        This tests:
        - Large payload handling
        - Token limit considerations
        - Processing of extensive transcripts
        """
        # Create a custom template with more detailed content
        custom_template = TestDataFactory.create_template(
            id="comprehensive_template",
            name="Comprehensive Session Summary",
            content="Create a comprehensive session summary including all topics discussed."
        )

        request_data = TestDataFactory.create_document_request(
            template=custom_template,
            transcript=TestDataFactory.create_large_transcript(segment_count=150),
            client_info=TestDataFactory.create_client_info(name="Long Session Client"),
            practitioner_info=TestDataFactory.create_practitioner_info(name="Dr. Patient Listener")
        )

        # Mock response for long transcript
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "# Comprehensive Session Summary\n\n" + ("Detailed content. " * 500)
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = Mock()
        mock_response.usage.total_tokens = 8000

        with patch('main.openai_client') as mock_openai:
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

            response = await async_client.post(
                "/generate-document-from-template",
                json=request_data,
                headers=TestDataFactory.create_headers()
            )

            assert response.status_code == 200
            response_data = response.json()

            assert "content" in response_data
            assert len(response_data["content"]) > 1000, "Should generate substantial content for long transcript"

            # Verify OpenAI received the full transcript
            call_args = mock_openai.chat.completions.create.call_args
            user_message = call_args[1]["messages"][1]["content"]
            assert "Segment" in user_message, "Transcript should be included in prompt"


class TestTemplateVariableSubstitution:
    """Tests for template variable substitution functionality"""

    async def test_basic_variable_substitution(self, async_client):
        """
        Test that template variables are properly substituted.

        Variables tested:
        - {{clientName}}
        - {{practitionerName}}
        - {{date}}

        Flow:
        1. Template contains {{clientName}}, {{practitionerName}}, {{date}}
        2. Variables should be replaced with actual values
        3. Generated document contains actual names and date

        This tests:
        - Variable detection and substitution
        - Name personalization
        - Date formatting
        """
        template_with_variables = TestDataFactory.create_template(
            content="""Progress Note for {{clientName}}

Practitioner: {{practitionerName}}
Date: {{date}}

Session conducted with {{clientName}} by {{practitionerName}}."""
        )

        request_data = TestDataFactory.create_document_request(
            template=template_with_variables,
            transcript=TestDataFactory.create_transcript(segment_count=5),
            client_info=TestDataFactory.create_client_info(name="Michael Torres"),
            practitioner_info=TestDataFactory.create_practitioner_info(name="Dr. Lisa Park")
        )

        # Mock OpenAI to return document with substituted variables
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = """Progress Note for Michael Torres

Practitioner: Dr. Lisa Park
Date: January 15, 2025

Session conducted with Michael Torres by Dr. Lisa Park."""
        mock_response.choices[0].finish_reason = "stop"

        with patch('main.openai_client') as mock_openai:
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

            response = await async_client.post(
                "/generate-document-from-template",
                json=request_data,
                headers=TestDataFactory.create_headers()
            )

            assert response.status_code == 200
            response_data = response.json()
            content = response_data["content"]

            # Verify variables were substituted (by OpenAI following instructions)
            assert "Michael Torres" in content, "Client name should be substituted"
            assert "Dr. Lisa Park" in content, "Practitioner name should be substituted"
            assert "January" in content or "2025" in content, "Date should be present"

            # Verify variables are NOT in the output
            assert "{{clientName}}" not in content, "Variable placeholder should be replaced"
            assert "{{practitionerName}}" not in content, "Variable placeholder should be replaced"
            assert "{{date}}" not in content, "Variable placeholder should be replaced"

    async def test_unicode_names_in_substitution(self, async_client):
        """
        Test variable substitution with Unicode characters in names.

        Flow:
        1. Use client/practitioner names with Unicode (José García, 李明, etc.)
        2. Variables should be substituted correctly
        3. Unicode preserved in output

        This tests:
        - Unicode handling
        - International character support
        - Encoding correctness
        """
        unicode_data = TestDataFactory.create_unicode_test_data()

        for name in unicode_data["names"][:3]:  # Test first 3 Unicode names
            request_data = TestDataFactory.create_document_request(
                template=TestDataFactory.create_template(
                    content="Session with {{clientName}} conducted by {{practitionerName}}."
                ),
                transcript=TestDataFactory.create_transcript(segment_count=3),
                client_info=TestDataFactory.create_client_info(name=name),
                practitioner_info=TestDataFactory.create_practitioner_info(name="Dr. Unicode Test")
            )

            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message = Mock()
            mock_response.choices[0].message.content = f"Session with {name} conducted by Dr. Unicode Test."
            mock_response.choices[0].finish_reason = "stop"

            with patch('main.openai_client') as mock_openai:
                mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

                response = await async_client.post(
                    "/generate-document-from-template",
                    json=request_data,
                    headers=TestDataFactory.create_headers()
                )

                assert response.status_code == 200
                response_data = response.json()

                # Verify Unicode name is in output
                assert name in response_data["content"], f"Unicode name '{name}' should be in document"


class TestDocumentRefinementWorkflow:
    """Tests for document modification and regeneration workflow"""

    async def test_document_regeneration_with_modifications(self, async_client):
        """
        Test the refinement workflow: generate → modify → regenerate.

        Flow:
        1. Generate initial document
        2. Send modification request (template contains "CRITICAL MODIFICATION REQUEST")
        3. OpenAI regenerates document with modifications
        4. Response contains updated document

        This tests:
        - Modification request detection
        - Regeneration flow
        - Preservation of original context
        """
        # First generation
        initial_request = TestDataFactory.create_document_request(
            template=TestDataFactory.create_safe_template(),
            transcript=TestDataFactory.create_transcript(segment_count=5),
            generation_instructions="Focus on anxiety management techniques"
        )

        initial_doc_content = "Initial document about anxiety management..."

        # Modification request (detected by "CRITICAL MODIFICATION REQUEST" prefix)
        modification_template = TestDataFactory.create_template(
            content=f"""CRITICAL MODIFICATION REQUEST

**Original Document:**
{initial_doc_content}

**Modification Instructions:**
Add a section about homework assignments discussed in the session.

**Important:** Preserve all existing content and add the new section at the end."""
        )

        modification_request = TestDataFactory.create_document_request(
            template=modification_template,
            transcript=TestDataFactory.create_transcript(segment_count=5),
            generation_instructions="Add homework section"
        )

        # Mock modified response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = initial_doc_content + "\n\n## Homework Assignments\n\n1. Practice mindfulness meditation daily\n2. Keep anxiety journal"
        mock_response.choices[0].finish_reason = "stop"

        with patch('main.openai_client') as mock_openai:
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

            response = await async_client.post(
                "/generate-document-from-template",
                json=modification_request,
                headers=TestDataFactory.create_headers()
            )

            assert response.status_code == 200
            response_data = response.json()
            content = response_data["content"]

            # Verify modification was applied
            assert "Homework Assignments" in content, "Modified section should be present"
            assert "mindfulness meditation" in content, "New content should be included"

            # Verify original content preserved
            assert initial_doc_content in content, "Original content should be preserved"

    async def test_regeneration_with_additional_context(self, async_client):
        """
        Test regeneration with additional context from practitioner.

        Flow:
        1. Generate document
        2. Practitioner provides additional context in generationInstructions
        3. System includes additional context in prompt
        4. Regenerated document incorporates new information

        This tests:
        - generationInstructions handling
        - Context integration
        - Document enhancement
        """
        request_data = TestDataFactory.create_document_request(
            template=TestDataFactory.create_safe_template(),
            transcript=TestDataFactory.create_transcript(segment_count=8),
            generation_instructions="The client mentioned trauma from childhood, but the transcript audio was unclear. Please note that the client discussed childhood trauma related to parental divorce at age 7."
        )

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = """# Session Summary

The client discussed childhood trauma related to parental divorce at age 7, which continues to impact current relationships. This background provides important context for treatment planning."""
        mock_response.choices[0].finish_reason = "stop"

        with patch('main.openai_client') as mock_openai:
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

            response = await async_client.post(
                "/generate-document-from-template",
                json=request_data,
                headers=TestDataFactory.create_headers()
            )

            assert response.status_code == 200
            response_data = response.json()
            content = response_data["content"]

            # Verify additional context was incorporated
            assert "childhood trauma" in content.lower(), "Additional context should be included"
            assert "parental divorce" in content.lower() or "divorce at age 7" in content.lower(), "Specific details should be present"

            # Verify system prompt included the additional instructions
            call_args = mock_openai.chat.completions.create.call_args
            system_prompt = call_args[1]["messages"][0]["content"]
            assert "ADDITIONAL CONTEXT" in system_prompt, "System prompt should include additional context section"


class TestConcurrentGeneration:
    """Tests for concurrent document generation scenarios"""

    async def test_concurrent_generation_different_clients(self, async_client):
        """
        Test concurrent document generation for different clients.

        Flow:
        1. Send 3 simultaneous requests for different clients
        2. Each request processed independently
        3. All responses contain correct client information
        4. No data leakage between requests

        This tests:
        - Concurrent request handling
        - Request isolation
        - Data integrity
        - Performance under load
        """
        clients = [
            TestDataFactory.create_client_info(id="client_001", name="Alice Anderson"),
            TestDataFactory.create_client_info(id="client_002", name="Bob Baker"),
            TestDataFactory.create_client_info(id="client_003", name="Carol Chen")
        ]

        # Create requests for each client
        requests = []
        for client in clients:
            request_data = TestDataFactory.create_document_request(
                template=TestDataFactory.create_safe_template(),
                transcript=TestDataFactory.create_transcript(segment_count=5),
                client_info=client,
                practitioner_info=TestDataFactory.create_practitioner_info()
            )
            requests.append(request_data)

        # Mock responses that include client names
        def create_mock_response(client_name: str):
            mock = Mock()
            mock.choices = [Mock()]
            mock.choices[0].message = Mock()
            mock.choices[0].message.content = f"Session document for {client_name}. Comprehensive notes about the session."
            mock.choices[0].finish_reason = "stop"
            return mock

        with patch('main.openai_client') as mock_openai:
            # Configure mock to return appropriate response based on client name
            async def mock_create(**kwargs):
                user_prompt = kwargs["messages"][1]["content"]
                for client in clients:
                    if client["name"] in user_prompt:
                        return create_mock_response(client["name"])
                return create_mock_response("Unknown")

            mock_openai.chat.completions.create = AsyncMock(side_effect=mock_create)

            # Send all requests concurrently
            tasks = []
            for request_data in requests:
                task = async_client.post(
                    "/generate-document-from-template",
                    json=request_data,
                    headers=TestDataFactory.create_headers()
                )
                tasks.append(task)

            responses = await asyncio.gather(*tasks)

            # Verify all succeeded
            assert all(r.status_code == 200 for r in responses), "All requests should succeed"

            # Verify each response contains correct client name
            for i, response in enumerate(responses):
                response_data = response.json()
                content = response_data["content"]
                expected_name = clients[i]["name"]

                assert expected_name in content, f"Response {i} should contain client name '{expected_name}'"

                # Verify no other client names present (no data leakage)
                other_names = [c["name"] for j, c in enumerate(clients) if j != i]
                for other_name in other_names:
                    assert other_name not in content, f"Response {i} should not contain other client name '{other_name}'"


class TestErrorHandlingAndResilience:
    """Tests for error handling and timeout scenarios"""

    async def test_openai_timeout_handling(self, async_client):
        """
        Test handling of OpenAI API timeout.

        Flow:
        1. OpenAI call times out
        2. System catches exception and returns 200 with error message
        3. User receives informative error message in content

        This tests:
        - Timeout handling
        - Graceful error handling
        - User-facing error messages

        Note: The implementation returns 200 with error content rather than 500
        to ensure the user receives a formatted error message.
        """
        request_data = TestDataFactory.create_document_request()

        with patch('main.openai_client') as mock_openai:
            # Simulate timeout
            mock_openai.chat.completions.create = AsyncMock(
                side_effect=asyncio.TimeoutError("OpenAI API timeout")
            )

            response = await async_client.post(
                "/generate-document-from-template",
                json=request_data,
                headers=TestDataFactory.create_headers()
            )

            # Implementation returns 200 with error content (graceful error handling)
            assert response.status_code == 200, "Should return 200 with error content"

            response_data = response.json()
            content = response_data.get("content", "")

            # Verify error message is user-friendly
            assert "timed out" in content.lower() or "timeout" in content.lower(), \
                "Content should explain the timeout issue"

    async def test_empty_openai_response_handling(self, async_client):
        """
        Test handling of empty response from OpenAI.

        Flow:
        1. OpenAI returns empty content
        2. System detects empty response
        3. Raises HTTPException with informative message

        This tests:
        - Response validation
        - Empty content detection
        - Error messaging
        """
        request_data = TestDataFactory.create_document_request()

        # Mock empty response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = ""  # Empty content
        mock_response.choices[0].finish_reason = "stop"

        with patch('main.openai_client') as mock_openai:
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

            response = await async_client.post(
                "/generate-document-from-template",
                json=request_data,
                headers=TestDataFactory.create_headers()
            )

            # Should return error
            assert response.status_code == 500, "Should return 500 for empty content"

            error_detail = response.json()["detail"]
            assert "No content was generated" in error_detail, "Error message should explain the issue"

    async def test_content_filter_response_handling(self, async_client):
        """
        Test handling of OpenAI content filter response.

        Flow:
        1. OpenAI returns content_filter finish_reason
        2. System detects content filtering
        3. Returns informative error to user

        This tests:
        - Content filter detection
        - Finish reason handling
        - User guidance on filtered content
        """
        request_data = TestDataFactory.create_document_request()

        # Mock content filter response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = None
        mock_response.choices[0].finish_reason = "content_filter"
        mock_response.usage = Mock()
        mock_response.usage.total_tokens = 150

        with patch('main.openai_client') as mock_openai:
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

            response = await async_client.post(
                "/generate-document-from-template",
                json=request_data,
                headers=TestDataFactory.create_headers()
            )

            assert response.status_code == 500
            error_detail = response.json()["detail"]

            # Verify error message mentions content filtering
            assert "filtered" in error_detail.lower(), "Error should mention content filtering"
            assert "safety system" in error_detail.lower(), "Error should reference safety system"

    async def test_missing_openai_client_handling(self, async_client):
        """
        Test handling when OpenAI client is not configured.

        Flow:
        1. OpenAI client is None
        2. System detects missing client
        3. Returns 500 error

        This tests:
        - Configuration validation
        - Graceful degradation
        - System readiness checks
        """
        request_data = TestDataFactory.create_document_request()

        with patch('main.openai_client', None):
            response = await async_client.post(
                "/generate-document-from-template",
                json=request_data,
                headers=TestDataFactory.create_headers()
            )

            assert response.status_code == 500
            error_detail = response.json()["detail"]
            assert "not configured" in error_detail.lower(), "Error should mention configuration issue"


class TestMetadataAndResponseStructure:
    """Tests for response metadata and structure validation"""

    async def test_response_includes_all_required_fields(self, async_client):
        """
        Test that response includes all required fields.

        Required fields:
        - content (string)
        - generatedAt (ISO timestamp)
        - metadata (dict)

        This tests:
        - Response structure
        - Field presence
        - Data types
        """
        request_data = TestDataFactory.create_document_request()

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Generated document content."
        mock_response.choices[0].finish_reason = "stop"

        with patch('main.openai_client') as mock_openai:
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

            response = await async_client.post(
                "/generate-document-from-template",
                json=request_data,
                headers=TestDataFactory.create_headers()
            )

            assert response.status_code == 200
            response_data = response.json()

            # Verify required fields
            assert "content" in response_data
            assert isinstance(response_data["content"], str)

            assert "generatedAt" in response_data
            assert isinstance(response_data["generatedAt"], str)
            # Verify it's a valid ISO timestamp
            datetime.fromisoformat(response_data["generatedAt"].replace('Z', '+00:00'))

            assert "metadata" in response_data
            assert isinstance(response_data["metadata"], dict)

    async def test_metadata_includes_template_info(self, async_client):
        """
        Test that metadata includes template and client information.

        Metadata should include:
        - templateId
        - templateName
        - clientId
        - practitionerId

        This tests:
        - Metadata population
        - Information preservation
        - Audit trail data
        """
        template = TestDataFactory.create_safe_template(
            id="template_123",
            name="Comprehensive Assessment"
        )
        client = TestDataFactory.create_client_info(id="client_456")
        practitioner = TestDataFactory.create_practitioner_info(id="prac_789")

        request_data = TestDataFactory.create_document_request(
            template=template,
            client_info=client,
            practitioner_info=practitioner
        )

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Document content."
        mock_response.choices[0].finish_reason = "stop"

        with patch('main.openai_client') as mock_openai:
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

            response = await async_client.post(
                "/generate-document-from-template",
                json=request_data,
                headers=TestDataFactory.create_headers()
            )

            assert response.status_code == 200
            metadata = response.json()["metadata"]

            # Verify metadata includes key information
            assert metadata.get("templateId") == "template_123"
            assert metadata.get("templateName") == "Comprehensive Assessment"
            assert metadata.get("clientId") == "client_456"
            assert metadata.get("practitionerId") == "prac_789"
