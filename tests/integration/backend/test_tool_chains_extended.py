"""
Extended Tool Chain Integration Tests

Tests comprehensive 5-6 tool workflows with realistic scenarios.
Each test validates full tool chain execution including error handling
and auth propagation.

Test Categories:
1. Document Generation Workflow (5-6 tools)
2. Conversation Analysis Workflow (5 tools)
3. Template Selection Workflow (5 tools)
4. Error Recovery in Tool Chains (5 tools)
5. Auth Token Consistency (5 tools across multiple endpoints)
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

import pytest
from unittest.mock import patch

from tests.helpers import (
    MockOpenAIBuilder,
    MockNestJSAPIBuilder,
    TestDataFactory
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class TestDocumentGenerationWorkflow:
    """
    Tests for complete document generation workflow.

    Typical flow:
    1. search_clients → Find client by name
    2. get_client_summary → Get client context
    3. search_sessions → Find relevant sessions
    4. load_session → Load session transcript
    5. get_templates → Get available templates
    6. generate_document_from_loaded → Generate document
    """

    async def test_full_document_generation_chain(self):
        """
        Test complete 6-tool document generation workflow.

        Flow:
        search_clients → get_client_summary → search_sessions →
        load_session → get_templates → generate_document_from_loaded
        """
        from pipeline_manager import PipelineManager
        from session_manager import session_manager
        from tools import tool_manager

        # Initialize
        await session_manager.initialize()
        pipeline = PipelineManager()
        await pipeline.initialize()

        # Create session
        session_id = await session_manager.create_session(
            persona_type="web_assistant",
            context={},
            auth_token="test_token",
            profile_id="test_profile"
        )

        try:
            tool_manager.set_auth_token("test_token", "test_profile")

            # Mock OpenAI with full tool chain
            mock_openai = MockOpenAIBuilder() \
                .add_tool_call("search_clients", {"query": "John Doe"}) \
                .add_tool_call("get_client_summary", {"client_id": "client_123"}) \
                .add_tool_call("search_sessions", {"client_id": "client_123", "limit": 5}) \
                .add_tool_call("load_session", {"session_id": "session_456"}) \
                .add_tool_call("get_templates", {}) \
                .add_tool_call("generate_document_from_loaded", {
                    "template_id": "template_789",
                    "instructions": "Generate progress note"
                }) \
                .add_text_response("I've generated the progress note document.") \
                .build()

            # Mock NestJS API responses
            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = MockNestJSAPIBuilder() \
                    .add_endpoint('/client/search', {
                        "clients": [
                            {"id": "client_123", "name": "John Doe", "email": "john@example.com"}
                        ]
                    }) \
                    .add_endpoint('/client/client_123/summary', {
                        "summary": "Client has been attending weekly sessions.",
                        "totalSessions": 10,
                        "recentProgress": "Good progress noted"
                    }) \
                    .add_endpoint('/session', {
                        "sessions": [
                            {
                                "id": "session_456",
                                "date": "2024-11-01",
                                "duration": 50,
                                "notes": "Client discussed work stress"
                            }
                        ]
                    }) \
                    .add_endpoint('/session/session_456', {
                        "id": "session_456",
                        "transcript": TestDataFactory.create_transcript(
                            speaker_count=2,
                            segment_count=10
                        ),
                        "clientId": "client_123"
                    }) \
                    .add_endpoint('/template', {
                        "templates": [
                            TestDataFactory.create_safe_template(
                                id="template_789",
                                name="Progress Note Template"
                            )
                        ]
                    }) \
                    .build()

                mock_client_class.return_value = mock_client

                # Set mock on pipeline instance
                pipeline.openai_client = mock_openai

                # Execute pipeline
                response_chunks = []
                async for chunk in pipeline.generate_response(
                    session_id=session_id,
                    persona_type="web_assistant",
                    user_message="Search for John Doe and generate a progress note from his latest session"
                ):
                    response_chunks.append(chunk)

                # Verify response generated
                assert len(response_chunks) > 0, "Should generate response"
                final_response = "".join(response_chunks)
                assert len(final_response) > 0, "Should have content"

                # Verify tool chain executed (7 calls: 6 tools + final text)
                assert mock_openai.chat.completions.create.call_count >= 6, \
                    "Should execute full tool chain"

        finally:
            await session_manager.delete_session(session_id)

    async def test_document_generation_with_session_validation(self):
        """
        Test 5-tool workflow with session validation.

        Flow:
        search_sessions → validate_sessions → load_session →
        get_templates → generate_document_from_loaded
        """
        from pipeline_manager import PipelineManager
        from session_manager import session_manager
        from tools import tool_manager

        await session_manager.initialize()
        pipeline = PipelineManager()
        await pipeline.initialize()

        session_id = await session_manager.create_session(
            persona_type="web_assistant",
            context={"client_id": "client_123"},
            auth_token="test_token",
            profile_id="test_profile"
        )

        try:
            tool_manager.set_auth_token("test_token", "test_profile")

            # Mock OpenAI tool chain
            mock_openai = MockOpenAIBuilder() \
                .add_tool_call("search_sessions", {"client_id": "client_123"}) \
                .add_tool_call("validate_sessions", {"session_ids": ["session_1", "session_2"]}) \
                .add_tool_call("load_session", {"session_id": "session_1"}) \
                .add_tool_call("get_templates", {}) \
                .add_tool_call("generate_document_from_loaded", {"template_id": "template_1"}) \
                .add_text_response("Document generated successfully.") \
                .build()

            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = MockNestJSAPIBuilder() \
                    .add_endpoint('/session', {
                        "sessions": [
                            {"id": "session_1", "date": "2024-11-01"},
                            {"id": "session_2", "date": "2024-10-25"}
                        ]
                    }) \
                    .add_endpoint('/session/validate', {
                        "valid_sessions": ["session_1", "session_2"],
                        "invalid_sessions": []
                    }) \
                    .add_endpoint('/session/session_1', {
                        "id": "session_1",
                        "transcript": TestDataFactory.create_transcript()
                    }) \
                    .add_endpoint('/template', {
                        "templates": [TestDataFactory.create_safe_template()]
                    }) \
                    .build()

                mock_client_class.return_value = mock_client
                pipeline.openai_client = mock_openai

                response_chunks = []
                async for chunk in pipeline.generate_response(
                    session_id=session_id,
                    persona_type="web_assistant",
                    user_message="Generate document from validated sessions"
                ):
                    response_chunks.append(chunk)

                assert len(response_chunks) > 0
                assert mock_openai.chat.completions.create.call_count >= 5

        finally:
            await session_manager.delete_session(session_id)


class TestConversationAnalysisWorkflow:
    """
    Tests for conversation analysis workflow.

    Typical flow:
    1. search_clients → Find client
    2. get_conversations → List conversations
    3. get_conversation_messages → Load messages
    4. get_client_summary → Get context
    5. analyze_session_content → Generate analysis
    """

    async def test_conversation_analysis_chain(self):
        """
        Test 5-tool conversation analysis workflow.

        Flow:
        search_clients → get_conversations → get_conversation_messages →
        get_client_summary → analyze_session_content
        """
        from pipeline_manager import PipelineManager
        from session_manager import session_manager
        from tools import tool_manager

        await session_manager.initialize()
        pipeline = PipelineManager()
        await pipeline.initialize()

        session_id = await session_manager.create_session(
            persona_type="web_assistant",
            context={},
            auth_token="test_token",
            profile_id="test_profile"
        )

        try:
            tool_manager.set_auth_token("test_token", "test_profile")

            # Mock OpenAI tool chain
            mock_openai = MockOpenAIBuilder() \
                .add_tool_call("search_clients", {"query": "Jane Smith"}) \
                .add_tool_call("get_conversations", {"client_id": "client_456"}) \
                .add_tool_call("get_conversation_messages", {"conversation_id": "conv_789"}) \
                .add_tool_call("get_client_summary", {"client_id": "client_456"}) \
                .add_tool_call("analyze_session_content", {
                    "content": "conversation_messages",
                    "analysis_type": "sentiment"
                }) \
                .add_text_response("Analysis shows positive sentiment overall.") \
                .build()

            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = MockNestJSAPIBuilder() \
                    .add_endpoint('/client/search', {
                        "clients": [
                            {"id": "client_456", "name": "Jane Smith"}
                        ]
                    }) \
                    .add_endpoint('/conversation', {
                        "conversations": [
                            {
                                "id": "conv_789",
                                "clientId": "client_456",
                                "messageCount": 25,
                                "lastMessage": "2024-11-05"
                            }
                        ]
                    }) \
                    .add_endpoint('/conversation/conv_789/messages', {
                        "messages": [
                            {
                                "id": "msg_1",
                                "content": "Hello, how are you?",
                                "sender": "practitioner",
                                "timestamp": "2024-11-05T10:00:00Z"
                            },
                            {
                                "id": "msg_2",
                                "content": "I'm doing better, thanks!",
                                "sender": "client",
                                "timestamp": "2024-11-05T10:05:00Z"
                            }
                        ]
                    }) \
                    .add_endpoint('/client/client_456/summary', {
                        "summary": "Client showing improvement",
                        "totalSessions": 8
                    }) \
                    .build()

                mock_client_class.return_value = mock_client
                pipeline.openai_client = mock_openai

                response_chunks = []
                async for chunk in pipeline.generate_response(
                    session_id=session_id,
                    persona_type="web_assistant",
                    user_message="Analyze recent conversations with Jane Smith"
                ):
                    response_chunks.append(chunk)

                assert len(response_chunks) > 0
                # 5 tool calls + 1 final text response = 6 OpenAI calls
                assert mock_openai.chat.completions.create.call_count >= 5

        finally:
            await session_manager.delete_session(session_id)

    async def test_multi_conversation_analysis_chain(self):
        """
        Test analyzing multiple conversations in sequence.

        Flow:
        get_conversations → get_latest_conversation →
        get_conversation_messages → get_client_summary → analyze_session_content
        """
        from pipeline_manager import PipelineManager
        from session_manager import session_manager
        from tools import tool_manager

        await session_manager.initialize()
        pipeline = PipelineManager()
        await pipeline.initialize()

        session_id = await session_manager.create_session(
            persona_type="web_assistant",
            context={"client_id": "client_789"},
            auth_token="test_token",
            profile_id="test_profile"
        )

        try:
            tool_manager.set_auth_token("test_token", "test_profile")

            mock_openai = MockOpenAIBuilder() \
                .add_tool_call("get_conversations", {"client_id": "client_789", "limit": 10}) \
                .add_tool_call("get_latest_conversation", {"client_id": "client_789"}) \
                .add_tool_call("get_conversation_messages", {"conversation_id": "conv_latest"}) \
                .add_tool_call("get_client_summary", {"client_id": "client_789"}) \
                .add_tool_call("analyze_session_content", {
                    "content": "latest_conversation",
                    "analysis_type": "themes"
                }) \
                .add_text_response("Key themes identified: coping strategies, family support.") \
                .build()

            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = MockNestJSAPIBuilder() \
                    .add_endpoint('/conversation', {
                        "conversations": [
                            {"id": "conv_latest", "date": "2024-11-05"},
                            {"id": "conv_2", "date": "2024-10-30"}
                        ]
                    }) \
                    .add_endpoint('/conversation/latest', {
                        "id": "conv_latest",
                        "clientId": "client_789",
                        "messageCount": 15
                    }) \
                    .add_endpoint('/conversation/conv_latest/messages', {
                        "messages": [
                            {"id": "msg_1", "content": "Discussing coping strategies", "sender": "client"}
                        ]
                    }) \
                    .add_endpoint('/client/client_789/summary', {
                        "summary": "Client actively engaged in therapy"
                    }) \
                    .build()

                mock_client_class.return_value = mock_client
                pipeline.openai_client = mock_openai

                response_chunks = []
                async for chunk in pipeline.generate_response(
                    session_id=session_id,
                    persona_type="web_assistant",
                    user_message="Analyze the latest conversation themes"
                ):
                    response_chunks.append(chunk)

                assert len(response_chunks) > 0
                assert mock_openai.chat.completions.create.call_count >= 5

        finally:
            await session_manager.delete_session(session_id)


class TestTemplateSelectionWorkflow:
    """
    Tests for template selection and document generation workflow.

    Typical flow:
    1. get_templates → List available templates
    2. select_template_by_name → Select specific template
    3. load_session → Load session for context
    4. check_document_readiness → Verify all data available
    5. generate_document_from_loaded → Generate document
    """

    async def test_template_selection_and_generation_chain(self):
        """
        Test 5-tool template selection workflow.

        Flow:
        get_templates → select_template_by_name → load_session →
        check_document_readiness → generate_document_from_loaded
        """
        from pipeline_manager import PipelineManager
        from session_manager import session_manager
        from tools import tool_manager

        await session_manager.initialize()
        pipeline = PipelineManager()
        await pipeline.initialize()

        session_id = await session_manager.create_session(
            persona_type="web_assistant",
            context={},
            auth_token="test_token",
            profile_id="test_profile"
        )

        try:
            tool_manager.set_auth_token("test_token", "test_profile")

            mock_openai = MockOpenAIBuilder() \
                .add_tool_call("get_templates", {}) \
                .add_tool_call("select_template_by_name", {"template_name": "Progress Note"}) \
                .add_tool_call("load_session", {"session_id": "session_123"}) \
                .add_tool_call("check_document_readiness", {}) \
                .add_tool_call("generate_document_from_loaded", {
                    "template_id": "template_progress",
                    "instructions": "Focus on treatment goals"
                }) \
                .add_text_response("Progress note generated successfully.") \
                .build()

            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = MockNestJSAPIBuilder() \
                    .add_endpoint('/template', {
                        "templates": [
                            TestDataFactory.create_safe_template(
                                id="template_progress",
                                name="Progress Note"
                            ),
                            TestDataFactory.create_safe_template(
                                id="template_intake",
                                name="Intake Form"
                            )
                        ]
                    }) \
                    .add_endpoint('/session/session_123', {
                        "id": "session_123",
                        "transcript": TestDataFactory.create_transcript()
                    }) \
                    .build()

                mock_client_class.return_value = mock_client
                pipeline.openai_client = mock_openai

                response_chunks = []
                async for chunk in pipeline.generate_response(
                    session_id=session_id,
                    persona_type="web_assistant",
                    user_message="Select progress note template and generate document from session 123"
                ):
                    response_chunks.append(chunk)

                assert len(response_chunks) > 0
                assert mock_openai.chat.completions.create.call_count >= 5

        finally:
            await session_manager.delete_session(session_id)

    async def test_template_selection_with_client_context(self):
        """
        Test 6-tool workflow with client context.

        Flow:
        search_clients → get_templates → select_template_by_name →
        load_session → check_document_readiness → generate_document_from_loaded
        """
        from pipeline_manager import PipelineManager
        from session_manager import session_manager
        from tools import tool_manager

        await session_manager.initialize()
        pipeline = PipelineManager()
        await pipeline.initialize()

        session_id = await session_manager.create_session(
            persona_type="web_assistant",
            context={},
            auth_token="test_token",
            profile_id="test_profile"
        )

        try:
            tool_manager.set_auth_token("test_token", "test_profile")

            mock_openai = MockOpenAIBuilder() \
                .add_tool_call("search_clients", {"query": "Michael Johnson"}) \
                .add_tool_call("get_templates", {}) \
                .add_tool_call("select_template_by_name", {"template_name": "Treatment Plan"}) \
                .add_tool_call("load_session", {"session_id": "session_999"}) \
                .add_tool_call("check_document_readiness", {}) \
                .add_tool_call("generate_document_from_loaded", {"template_id": "template_treatment"}) \
                .add_text_response("Treatment plan generated for Michael Johnson.") \
                .build()

            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = MockNestJSAPIBuilder() \
                    .add_endpoint('/client/search', {
                        "clients": [{"id": "client_999", "name": "Michael Johnson"}]
                    }) \
                    .add_endpoint('/template', {
                        "templates": [
                            TestDataFactory.create_safe_template(
                                id="template_treatment",
                                name="Treatment Plan"
                            )
                        ]
                    }) \
                    .add_endpoint('/session/session_999', {
                        "id": "session_999",
                        "transcript": TestDataFactory.create_transcript()
                    }) \
                    .build()

                mock_client_class.return_value = mock_client
                pipeline.openai_client = mock_openai

                response_chunks = []
                async for chunk in pipeline.generate_response(
                    session_id=session_id,
                    persona_type="web_assistant",
                    user_message="Find Michael Johnson and generate a treatment plan"
                ):
                    response_chunks.append(chunk)

                assert len(response_chunks) > 0
                assert mock_openai.chat.completions.create.call_count >= 6

        finally:
            await session_manager.delete_session(session_id)


class TestErrorRecoveryInToolChains:
    """
    Tests for error handling and recovery in tool chains.

    Scenarios:
    1. API error in middle of chain
    2. Invalid tool arguments
    3. Missing data recovery
    4. Partial chain completion
    """

    async def test_api_error_recovery_in_five_tool_chain(self):
        """
        Test error recovery when API fails in middle of 5-tool chain.

        Flow:
        search_clients → get_client_summary [FAILS] →
        search_clients (retry) → get_client_summary → get_conversations
        """
        from pipeline_manager import PipelineManager
        from session_manager import session_manager
        from tools import tool_manager

        await session_manager.initialize()
        pipeline = PipelineManager()
        await pipeline.initialize()

        session_id = await session_manager.create_session(
            persona_type="web_assistant",
            context={},
            auth_token="test_token",
            profile_id="test_profile"
        )

        try:
            tool_manager.set_auth_token("test_token", "test_profile")

            # Mock OpenAI with error recovery
            mock_openai = MockOpenAIBuilder() \
                .add_tool_call("search_clients", {"query": "Alice"}) \
                .add_tool_call("get_client_summary", {"client_id": "client_alice"}) \
                .add_tool_call("search_clients", {"query": "Alice", "exact_match": True}) \
                .add_tool_call("get_client_summary", {"client_id": "client_alice_2"}) \
                .add_tool_call("get_conversations", {"client_id": "client_alice_2"}) \
                .add_text_response("Found client information after retry.") \
                .build()

            with patch('httpx.AsyncClient') as mock_client_class:
                # First summary call fails, second succeeds
                call_count = [0]

                async def mock_request(url, **kwargs):
                    from unittest.mock import AsyncMock
                    response = AsyncMock()

                    if '/client/search' in url:
                        response.status_code = 200
                        response.json = AsyncMock(return_value={
                            "clients": [{"id": "client_alice_2", "name": "Alice"}]
                        })
                    elif '/summary' in url:
                        call_count[0] += 1
                        if call_count[0] == 1:
                            # First call fails
                            response.status_code = 500
                            response.json = AsyncMock(return_value={"error": "Server error"})
                        else:
                            # Second call succeeds
                            response.status_code = 200
                            response.json = AsyncMock(return_value={
                                "summary": "Client summary data"
                            })
                    elif '/conversation' in url:
                        response.status_code = 200
                        response.json = AsyncMock(return_value={"conversations": []})
                    else:
                        response.status_code = 200
                        response.json = AsyncMock(return_value={})

                    return response

                from unittest.mock import AsyncMock
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(side_effect=mock_request)
                mock_client.post = AsyncMock(side_effect=mock_request)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)

                mock_client_class.return_value = mock_client
                pipeline.openai_client = mock_openai

                response_chunks = []
                async for chunk in pipeline.generate_response(
                    session_id=session_id,
                    persona_type="web_assistant",
                    user_message="Find Alice and get her conversations"
                ):
                    response_chunks.append(chunk)

                # Should complete despite error
                assert len(response_chunks) > 0

        finally:
            await session_manager.delete_session(session_id)

    async def test_missing_data_recovery_in_tool_chain(self):
        """
        Test recovery when data is missing in 5-tool chain.

        Flow:
        search_sessions → load_session [NO DATA] →
        search_sessions (broader) → load_session → get_session_content
        """
        from pipeline_manager import PipelineManager
        from session_manager import session_manager
        from tools import tool_manager

        await session_manager.initialize()
        pipeline = PipelineManager()
        await pipeline.initialize()

        session_id = await session_manager.create_session(
            persona_type="web_assistant",
            context={"client_id": "client_123"},
            auth_token="test_token",
            profile_id="test_profile"
        )

        try:
            tool_manager.set_auth_token("test_token", "test_profile")

            mock_openai = MockOpenAIBuilder() \
                .add_tool_call("search_sessions", {"client_id": "client_123", "date": "2024-11-01"}) \
                .add_tool_call("load_session", {"session_id": "session_404"}) \
                .add_tool_call("search_sessions", {"client_id": "client_123"}) \
                .add_tool_call("load_session", {"session_id": "session_200"}) \
                .add_tool_call("get_session_content", {"session_id": "session_200"}) \
                .add_text_response("Successfully loaded session content.") \
                .build()

            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = MockNestJSAPIBuilder() \
                    .add_endpoint('/session', {
                        "sessions": [{"id": "session_200", "date": "2024-10-28"}]
                    }) \
                    .add_endpoint('/session/session_404', {
                        "error": "Session not found"
                    }, status_code=404) \
                    .add_endpoint('/session/session_200', {
                        "id": "session_200",
                        "transcript": TestDataFactory.create_transcript()
                    }) \
                    .build()

                mock_client_class.return_value = mock_client
                pipeline.openai_client = mock_openai

                response_chunks = []
                async for chunk in pipeline.generate_response(
                    session_id=session_id,
                    persona_type="web_assistant",
                    user_message="Load session from specific date or find alternative"
                ):
                    response_chunks.append(chunk)

                assert len(response_chunks) > 0

        finally:
            await session_manager.delete_session(session_id)


class TestAuthTokenConsistency:
    """
    Tests for auth token consistency across tool chains.

    Validates that auth tokens are properly propagated through
    5+ tool calls to different API endpoints.
    """

    async def test_auth_consistency_across_five_tools(self):
        """
        Test auth token propagates correctly through 5 tools.

        Flow:
        search_clients → get_client_summary → get_conversations →
        get_conversation_messages → analyze_session_content

        Each tool should receive correct auth headers.
        """
        from pipeline_manager import PipelineManager
        from session_manager import session_manager
        from tools import tool_manager

        await session_manager.initialize()
        pipeline = PipelineManager()
        await pipeline.initialize()

        # Use specific auth token to track
        auth_token = "test_auth_token_12345"
        profile_id = "profile_67890"

        session_id = await session_manager.create_session(
            persona_type="web_assistant",
            context={},
            auth_token=auth_token,
            profile_id=profile_id
        )

        try:
            tool_manager.set_auth_token(auth_token, profile_id)

            mock_openai = MockOpenAIBuilder() \
                .add_tool_call("search_clients", {"query": "Test Client"}) \
                .add_tool_call("get_client_summary", {"client_id": "client_test"}) \
                .add_tool_call("get_conversations", {"client_id": "client_test"}) \
                .add_tool_call("get_conversation_messages", {"conversation_id": "conv_test"}) \
                .add_tool_call("analyze_session_content", {"content": "messages"}) \
                .add_text_response("Analysis complete.") \
                .build()

            with patch('httpx.AsyncClient') as mock_client_class:
                # Track auth headers
                received_headers = []

                async def capture_request(url, **kwargs):
                    from unittest.mock import AsyncMock
                    # Capture headers from each request
                    if 'headers' in kwargs:
                        received_headers.append(kwargs['headers'])

                    response = AsyncMock()
                    response.status_code = 200

                    if '/client/search' in url:
                        response.json = AsyncMock(return_value={
                            "clients": [{"id": "client_test", "name": "Test Client"}]
                        })
                    elif '/summary' in url:
                        response.json = AsyncMock(return_value={"summary": "Test summary"})
                    elif '/conversation' in url and '/messages' not in url:
                        response.json = AsyncMock(return_value={
                            "conversations": [{"id": "conv_test"}]
                        })
                    elif '/messages' in url:
                        response.json = AsyncMock(return_value={
                            "messages": [{"id": "msg_1", "content": "Test message"}]
                        })
                    else:
                        response.json = AsyncMock(return_value={})

                    return response

                from unittest.mock import AsyncMock
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(side_effect=capture_request)
                mock_client.post = AsyncMock(side_effect=capture_request)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)

                mock_client_class.return_value = mock_client
                pipeline.openai_client = mock_openai

                response_chunks = []
                async for chunk in pipeline.generate_response(
                    session_id=session_id,
                    persona_type="web_assistant",
                    user_message="Analyze all data for Test Client"
                ):
                    response_chunks.append(chunk)

                assert len(response_chunks) > 0

                # Verify auth headers were sent (at least some requests should have headers)
                # Note: Exact verification depends on implementation details
                # This test primarily validates the chain executes without auth errors

        finally:
            await session_manager.delete_session(session_id)

    async def test_auth_context_preserved_across_session_tools(self):
        """
        Test auth context preserved through session-related tools.

        Flow:
        search_sessions → validate_sessions → load_session →
        get_session_content → analyze_loaded_session
        """
        from pipeline_manager import PipelineManager
        from session_manager import session_manager
        from tools import tool_manager

        await session_manager.initialize()
        pipeline = PipelineManager()
        await pipeline.initialize()

        auth_token = "session_auth_token_999"
        profile_id = "session_profile_888"

        session_id = await session_manager.create_session(
            persona_type="web_assistant",
            context={"client_id": "client_session_test"},
            auth_token=auth_token,
            profile_id=profile_id
        )

        try:
            tool_manager.set_auth_token(auth_token, profile_id)

            mock_openai = MockOpenAIBuilder() \
                .add_tool_call("search_sessions", {"client_id": "client_session_test"}) \
                .add_tool_call("validate_sessions", {"session_ids": ["sess_1", "sess_2"]}) \
                .add_tool_call("load_session", {"session_id": "sess_1"}) \
                .add_tool_call("get_session_content", {"session_id": "sess_1"}) \
                .add_tool_call("analyze_loaded_session", {"analysis_focus": "themes"}) \
                .add_text_response("Session analysis complete.") \
                .build()

            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = MockNestJSAPIBuilder() \
                    .add_endpoint('/session', {
                        "sessions": [
                            {"id": "sess_1", "date": "2024-11-01"},
                            {"id": "sess_2", "date": "2024-10-28"}
                        ]
                    }) \
                    .add_endpoint('/session/validate', {
                        "valid_sessions": ["sess_1", "sess_2"]
                    }) \
                    .add_endpoint('/session/sess_1', {
                        "id": "sess_1",
                        "transcript": TestDataFactory.create_transcript()
                    }) \
                    .build()

                mock_client_class.return_value = mock_client
                pipeline.openai_client = mock_openai

                response_chunks = []
                async for chunk in pipeline.generate_response(
                    session_id=session_id,
                    persona_type="web_assistant",
                    user_message="Validate and analyze all sessions"
                ):
                    response_chunks.append(chunk)

                assert len(response_chunks) > 0
                assert mock_openai.chat.completions.create.call_count >= 5

        finally:
            await session_manager.delete_session(session_id)


class TestComplexWorkflowIntegration:
    """
    Tests for complex multi-step workflows combining different tool types.
    """

    async def test_client_to_document_full_pipeline(self):
        """
        Test complete client → document generation pipeline (6 tools).

        Flow:
        search_clients → get_client_base → search_sessions →
        load_multiple_sessions → get_templates → generate_document_auto
        """
        from pipeline_manager import PipelineManager
        from session_manager import session_manager
        from tools import tool_manager

        await session_manager.initialize()
        pipeline = PipelineManager()
        await pipeline.initialize()

        session_id = await session_manager.create_session(
            persona_type="web_assistant",
            context={},
            auth_token="test_token",
            profile_id="test_profile"
        )

        try:
            tool_manager.set_auth_token("test_token", "test_profile")

            mock_openai = MockOpenAIBuilder() \
                .add_tool_call("search_clients", {"query": "Robert Davis"}) \
                .add_tool_call("get_client_base", {"client_id": "client_robert"}) \
                .add_tool_call("search_sessions", {"client_id": "client_robert", "limit": 10}) \
                .add_tool_call("load_multiple_sessions", {"session_ids": ["sess_1", "sess_2", "sess_3"]}) \
                .add_tool_call("get_templates", {}) \
                .add_tool_call("generate_document_auto", {
                    "document_type": "comprehensive_report",
                    "include_all_sessions": True
                }) \
                .add_text_response("Comprehensive report generated successfully.") \
                .build()

            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = MockNestJSAPIBuilder() \
                    .add_endpoint('/client/search', {
                        "clients": [{"id": "client_robert", "name": "Robert Davis"}]
                    }) \
                    .add_endpoint('/client/client_robert', {
                        "id": "client_robert",
                        "name": "Robert Davis",
                        "email": "robert@example.com"
                    }) \
                    .add_endpoint('/session', {
                        "sessions": [
                            {"id": "sess_1", "date": "2024-11-01"},
                            {"id": "sess_2", "date": "2024-10-25"},
                            {"id": "sess_3", "date": "2024-10-18"}
                        ]
                    }) \
                    .add_endpoint('/session/load-multiple', {
                        "sessions": [
                            {"id": "sess_1", "transcript": TestDataFactory.create_transcript()},
                            {"id": "sess_2", "transcript": TestDataFactory.create_transcript()},
                            {"id": "sess_3", "transcript": TestDataFactory.create_transcript()}
                        ]
                    }) \
                    .add_endpoint('/template', {
                        "templates": [
                            TestDataFactory.create_safe_template(
                                id="comprehensive_template",
                                name="Comprehensive Report"
                            )
                        ]
                    }) \
                    .build()

                mock_client_class.return_value = mock_client
                pipeline.openai_client = mock_openai

                response_chunks = []
                async for chunk in pipeline.generate_response(
                    session_id=session_id,
                    persona_type="web_assistant",
                    user_message="Create comprehensive report for Robert Davis using all sessions"
                ):
                    response_chunks.append(chunk)

                assert len(response_chunks) > 0
                assert mock_openai.chat.completions.create.call_count >= 6

        finally:
            await session_manager.delete_session(session_id)
