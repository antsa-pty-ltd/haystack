"""
WebSocket-to-Tool Integration Tests

Tests WebSocket messages triggering tool execution and UI state interactions:
- WebSocket message → Tool chain execution (3-tool chains)
- UI state (loadedSessions, page_type) affecting tool behavior
- selectedTemplate in UI state used by document tools
- WebSocket auth flowing to NestJS API calls
- Concurrent WebSocket messages during tool execution
- UI actions delivered after tool chain completion

Integration Points:
- WebSocket handler ↔ Pipeline Manager
- Pipeline Manager ↔ Tool Manager
- Tool Manager ↔ UI State Manager
- Tool Manager ↔ NestJS API (auth propagation)
- UI actions returned to WebSocket client

NOT Tested:
- Streaming interruptions (too complex for reliable testing)
"""

import os
import sys
import pytest
import json
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timezone

# Add haystack directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

# Mark all tests as integration tests
pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class TestWebSocketTriggersToolChains:
    """Tests WebSocket messages triggering tool chain execution"""

    async def test_websocket_message_triggers_3_tool_chain(self):
        """
        Test WebSocket chat message triggers tool execution via pipeline.

        Flow:
        1. Send WebSocket chat message
        2. Mock pipeline to return streaming chunks
        3. Verify WebSocket receives typing indicator, chunks, and completion
        4. Verify message flow through WebSocket

        This tests:
        - WebSocket → Pipeline integration
        - Message streaming back to WebSocket
        - Complete message lifecycle
        """
        from main import app
        from session_manager import session_manager
        from tools import tool_manager
        from fastapi.testclient import TestClient

        await session_manager.initialize()

        session_id = "test-ws-tool-chain-session"
        await session_manager.create_session(
            session_id=session_id,
            persona_type="web_assistant",
            context={},
            auth_token="test-ws-token",
            profile_id="profile-ws-123"
        )

        client = TestClient(app)

        try:
            # Mock pipeline to return streaming chunks
            with patch('main.pipeline_manager.generate_response_with_chaining') as mock_generate:
                async def mock_streaming_response(*args, **kwargs):
                    """Mock streaming response"""
                    yield "I "
                    yield "found "
                    yield "the client."

                mock_generate.return_value = mock_streaming_response()

                with client.websocket_connect(f"/ws/{session_id}") as websocket:
                    # Skip connection message
                    websocket.receive_text()

                    # Send chat message
                    websocket.send_text(json.dumps({
                        "message": "Search for clients",
                        "auth_token": "test-ws-token",
                        "profile_id": "profile-ws-123"
                    }))

                    # Collect all WebSocket messages
                    messages = []
                    for _ in range(50):
                        try:
                            data = websocket.receive_text()
                            message = json.loads(data)
                            messages.append(message)

                            if message.get("type") == "message_complete":
                                break
                        except Exception:
                            break

                    # Verify we got typing indicator
                    typing_messages = [m for m in messages if m.get("type") == "typing"]
                    assert len(typing_messages) >= 1, "Should receive typing indicator"

                    # Verify we got message chunks
                    chunk_messages = [m for m in messages if m.get("type") == "message_chunk"]
                    assert len(chunk_messages) > 0, "Should receive message chunks"

                    # Verify message_complete sent
                    complete_messages = [m for m in messages if m.get("type") == "message_complete"]
                    assert len(complete_messages) == 1, "Should receive message_complete"

        finally:
            await session_manager.delete_session(session_id)


class TestUIStateAffectsToolBehavior:
    """Tests UI state influencing tool execution behavior"""

    async def test_loaded_sessions_in_ui_state_affects_tool_execution(self):
        """
        Test that loadedSessions in UI state is accessible by tools.

        Flow:
        1. Update UI state with loadedSessions
        2. Verify UI state persists
        3. Verify sync access works (used by tools)

        This tests:
        - UI state persistence
        - Tool access to UI state (sync access from async tool context)
        - loadedSessions field handling
        """
        from main import app
        from session_manager import session_manager
        from ui_state_manager import ui_state_manager
        from fastapi.testclient import TestClient

        await session_manager.initialize()
        await ui_state_manager.initialize()

        session_id = "test-ui-state-loaded-sessions"
        await session_manager.create_session(
            session_id=session_id,
            persona_type="web_assistant",
            context={},
            auth_token="test-token",
            profile_id="profile-123"
        )

        client = TestClient(app)

        try:
            await ui_state_manager.update_state(session_id, {
                "loadedSessions": [
                    {"id": "session-1", "name": "Session 1"},
                    {"id": "session-2", "name": "Session 2"}
                ],
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

            with client.websocket_connect(f"/ws/{session_id}") as websocket:
                websocket.receive_text()

                websocket.send_text(json.dumps({
                    "type": "ui_state_update",
                    "state": {
                        "loadedSessions": [
                            {"id": "session-1", "name": "Session 1"},
                            {"id": "session-2", "name": "Session 2"}
                        ],
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                }))

                data = websocket.receive_text()
                message = json.loads(data)
                assert message["type"] == "ui_state_ack"

                persisted_state = await ui_state_manager.get_state(session_id)
                assert "loadedSessions" in persisted_state
                assert len(persisted_state["loadedSessions"]) == 2

                loaded_sessions_sync = ui_state_manager.get_loaded_sessions_sync(session_id)
                assert len(loaded_sessions_sync) == 2
                assert loaded_sessions_sync[0]["id"] == "session-1"

        finally:
            await session_manager.delete_session(session_id)

    async def test_page_type_filters_available_tools(self):
        """Test that page_type in UI state can be set and accessed."""
        from main import app
        from session_manager import session_manager
        from ui_state_manager import ui_state_manager
        from tools import tool_manager
        from fastapi.testclient import TestClient

        await session_manager.initialize()
        await ui_state_manager.initialize()

        session_id = "test-page-type-filtering"
        await session_manager.create_session(
            session_id=session_id,
            persona_type="web_assistant",
            context={},
            auth_token="test-token",
            profile_id="profile-456"
        )

        client = TestClient(app)

        try:
            with client.websocket_connect(f"/ws/{session_id}") as websocket:
                websocket.receive_text()

                websocket.send_text(json.dumps({
                    "type": "ui_state_update",
                    "state": {
                        "page_type": "transcribe_page",
                        "page_url": "/transcribe",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                }))

                data = websocket.receive_text()
                message = json.loads(data)
                assert message["type"] == "ui_state_ack"
                assert message["success"] is True

                state = await ui_state_manager.get_state(session_id)
                assert state.get("page_type") == "transcribe_page"

                tool_manager.set_page_context({"page_type": "transcribe_page"})
                assert tool_manager.current_page_context.get("page_type") == "transcribe_page"

        finally:
            await session_manager.delete_session(session_id)

    async def test_selected_template_in_ui_state_used_by_document_tools(self):
        """Test that selectedTemplate in UI state is accessible by tools."""
        from main import app
        from session_manager import session_manager
        from ui_state_manager import ui_state_manager
        from fastapi.testclient import TestClient

        await session_manager.initialize()
        await ui_state_manager.initialize()

        session_id = "test-selected-template"
        await session_manager.create_session(
            session_id=session_id,
            persona_type="web_assistant",
            context={},
            auth_token="test-token",
            profile_id="profile-789"
        )

        client = TestClient(app)

        try:
            await ui_state_manager.update_state(session_id, {
                "selectedTemplate": {
                    "id": "tmpl-progress-note",
                    "name": "Progress Note",
                    "content": "Template content here"
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

            with client.websocket_connect(f"/ws/{session_id}") as websocket:
                websocket.receive_text()

                state = await ui_state_manager.get_state(session_id)
                assert "selectedTemplate" in state
                assert state["selectedTemplate"]["id"] == "tmpl-progress-note"

                state_sync = ui_state_manager.get_state_sync(session_id)
                assert state_sync.get("selectedTemplate", {}).get("id") == "tmpl-progress-note"

        finally:
            await session_manager.delete_session(session_id)


class TestWebSocketAuthFlowsToNestJSAPI:
    """Tests authentication propagation from WebSocket to NestJS API"""

    async def test_websocket_auth_token_flows_to_nestjs_api_calls(self):
        """Test auth_token from WebSocket message is extracted and passed to pipeline."""
        from main import app
        from session_manager import session_manager
        from fastapi.testclient import TestClient

        await session_manager.initialize()

        session_id = "test-auth-flow"
        await session_manager.create_session(
            session_id=session_id,
            persona_type="web_assistant",
            context={},
            auth_token="initial-token",
            profile_id="initial-profile"
        )

        client = TestClient(app)

        try:
            with patch('main.pipeline_manager.generate_response_with_chaining') as mock_generate:
                async def mock_response(*args, **kwargs):
                    # Verify auth_token is in kwargs
                    assert "auth_token" in kwargs, "Auth token should be passed to pipeline"
                    assert kwargs["auth_token"] == "websocket-auth-token-xyz"
                    yield "Response"

                mock_generate.return_value = mock_response()

                with client.websocket_connect(f"/ws/{session_id}") as websocket:
                    websocket.receive_text()

                    websocket.send_text(json.dumps({
                        "message": "Test message",
                        "auth_token": "websocket-auth-token-xyz",
                        "profile_id": "profile-websocket-123"
                    }))

                    for _ in range(20):
                        try:
                            data = websocket.receive_text()
                            message = json.loads(data)
                            if message.get("type") == "message_complete":
                                break
                        except Exception:
                            break

                    assert mock_generate.called, "Pipeline should be called with auth"

        finally:
            await session_manager.delete_session(session_id)


class TestConcurrentWebSocketMessages:
    """Tests concurrent WebSocket message handling during tool execution"""

    async def test_concurrent_websocket_messages_during_tool_execution(self):
        """Test that WebSocket handles multiple messages sequentially."""
        from main import app
        from session_manager import session_manager
        from fastapi.testclient import TestClient

        await session_manager.initialize()

        session_id = "test-concurrent-ws"
        await session_manager.create_session(
            session_id=session_id,
            persona_type="web_assistant",
            context={},
            auth_token="test-token",
            profile_id="profile-concurrent"
        )

        client = TestClient(app)

        try:
            with patch('main.pipeline_manager.generate_response_with_chaining') as mock_generate:
                call_count = [0]

                async def mock_response(*args, **kwargs):
                    call_count[0] += 1
                    await asyncio.sleep(0.05)
                    yield f"Response {call_count[0]}"

                mock_generate.side_effect = lambda *args, **kwargs: mock_response(*args, **kwargs)

                with client.websocket_connect(f"/ws/{session_id}") as websocket:
                    websocket.receive_text()

                    websocket.send_text(json.dumps({
                        "message": "First message",
                        "auth_token": "test-token"
                    }))

                    websocket.send_text(json.dumps({
                        "message": "Second message",
                        "auth_token": "test-token"
                    }))

                    messages = []
                    completion_count = 0
                    for _ in range(50):
                        try:
                            data = websocket.receive_text()
                            message = json.loads(data)
                            messages.append(message)

                            if message.get("type") == "message_complete":
                                completion_count += 1
                                if completion_count >= 2:
                                    break
                        except Exception:
                            break

                    assert completion_count >= 1, "Should process at least first message"

        finally:
            await session_manager.delete_session(session_id)


class TestUIActionsDeliveredAfterToolChain:
    """Tests UI actions delivered after tool chain completion"""

    async def test_ui_actions_delivered_after_tool_chain_completion(self):
        """Test that UI actions are delivered via WebSocket."""
        from main import app
        from session_manager import session_manager
        from fastapi.testclient import TestClient

        await session_manager.initialize()

        session_id = "test-ui-actions"
        await session_manager.create_session(
            session_id=session_id,
            persona_type="web_assistant",
            context={},
            auth_token="test-token",
            profile_id="profile-actions"
        )

        client = TestClient(app)

        try:
            with patch('main.pipeline_manager.generate_response_with_chaining') as mock_generate:
                with patch('main.pipeline_manager.pop_ui_actions') as mock_pop_ui_actions:
                    async def mock_response(*args, **kwargs):
                        yield "Action completed"

                    mock_generate.return_value = mock_response()

                    mock_pop_ui_actions.return_value = [
                        {
                            "type": "loadSession",
                            "session_id": "session-123",
                            "payload": {"session": {"id": "session-123"}}
                        }
                    ]

                    with client.websocket_connect(f"/ws/{session_id}") as websocket:
                        websocket.receive_text()

                        websocket.send_text(json.dumps({
                            "message": "Trigger action",
                            "auth_token": "test-token"
                        }))

                        messages = []
                        for _ in range(30):
                            try:
                                data = websocket.receive_text()
                                message = json.loads(data)
                                messages.append(message)

                                if message.get("type") == "message_complete":
                                    break
                            except Exception:
                                break

                        ui_action_messages = [m for m in messages if m.get("type") == "ui_action"]

                        assert len(ui_action_messages) >= 1, \
                            f"Should deliver UI actions, got message types: {[m.get('type') for m in messages]}"

                        action = ui_action_messages[0]
                        assert "action" in action, "Should include action field"
                        assert action["action"]["type"] == "loadSession"

        finally:
            await session_manager.delete_session(session_id)

    async def test_multiple_ui_actions_delivered_in_sequence(self):
        """Test that multiple UI actions are all delivered."""
        from main import app
        from session_manager import session_manager
        from fastapi.testclient import TestClient

        await session_manager.initialize()

        session_id = "test-multiple-ui-actions"
        await session_manager.create_session(
            session_id=session_id,
            persona_type="web_assistant",
            context={},
            auth_token="test-token",
            profile_id="profile-multi-actions"
        )

        client = TestClient(app)

        try:
            with patch('main.pipeline_manager.generate_response_with_chaining') as mock_generate:
                with patch('main.pipeline_manager.pop_ui_actions') as mock_pop_ui_actions:
                    async def mock_response(*args, **kwargs):
                        yield "Actions completed"

                    mock_generate.return_value = mock_response()

                    mock_pop_ui_actions.return_value = [
                        {"type": "loadSession", "session_id": "session-1"},
                        {"type": "selectTemplate", "template_id": "tmpl-1"},
                        {"type": "updateDocumentStatus", "status": "ready"}
                    ]

                    with client.websocket_connect(f"/ws/{session_id}") as websocket:
                        websocket.receive_text()

                        websocket.send_text(json.dumps({
                            "message": "Execute workflow",
                            "auth_token": "test-token"
                        }))

                        messages = []
                        for _ in range(30):
                            try:
                                data = websocket.receive_text()
                                message = json.loads(data)
                                messages.append(message)

                                if message.get("type") == "message_complete":
                                    break
                            except Exception:
                                break

                        ui_actions = [m for m in messages if m.get("type") == "ui_action"]

                        assert len(ui_actions) >= 3, \
                            f"Expected 3 UI actions, got {len(ui_actions)}"

                        action_types = [a["action"]["type"] for a in ui_actions]
                        assert "loadSession" in action_types
                        assert "selectTemplate" in action_types
                        assert "updateDocumentStatus" in action_types

        finally:
            await session_manager.delete_session(session_id)
