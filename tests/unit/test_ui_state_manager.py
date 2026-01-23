"""Unit tests for UI State Manager."""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock

import sys
sys.path.insert(0, '.')
from ui_state_manager import UIStateManager, UIState


@pytest.fixture
def ui_manager():
    """Create a fresh UIStateManager in-memory mode."""
    return UIStateManager()


@pytest.fixture
def initialized_ui_manager():
    """Create a UIStateManager with mocked Redis clients."""
    manager = UIStateManager()
    manager._initialized = True
    manager.redis_client = AsyncMock()
    manager.redis_client_sync = MagicMock()
    return manager


@pytest.fixture
def sample_ui_state() -> UIState:
    """Sample UI state for testing."""
    return {
        "session_id": "test-session-123",
        "last_updated": "2026-01-23T10:00:00Z",
        "page_type": "transcribe_page",
        "page_url": "/transcribe",
        "loadedSessions": [{
            "sessionId": "sess-001",
            "clientId": "client-001",
            "clientName": "John Doe",
            "content": "Session content here",
            "metadata": {"duration": 3600}
        }],
        "currentClient": {"clientId": "client-001", "clientName": "John Doe"},
        "selectedTemplate": {
            "templateId": "template-001",
            "templateName": "Session Notes",
            "templateContent": "# Session Notes\n...",
            "templateDescription": "Standard notes"
        },
        "generatedDocuments": [],
        "sessionCount": 1,
        "documentCount": 0,
        "client_id": "client-001",
        "client_name": "John Doe",
        "active_tab": "transcribe",
        "profile_id": "profile-001"
    }

@pytest.mark.unit
class TestKeyGeneration:
    """Test Redis key generation methods."""

    def test_state_key_format(self, ui_manager):
        assert ui_manager._state_key("session-123") == "ui_state:session-123"

    def test_token_key_format(self, ui_manager):
        assert ui_manager._token_key("session-123") == "auth_token:session-123"

    def test_state_key_handles_special_chars(self, ui_manager):
        key = ui_manager._state_key("session-with-dashes_and_underscores")
        assert key == "ui_state:session-with-dashes_and_underscores"


@pytest.mark.unit
class TestInMemoryFallback:
    """Test in-memory storage when Redis is not available."""

    @pytest.mark.asyncio
    async def test_update_state_stores_in_memory(self, ui_manager, sample_ui_state):
        result = await ui_manager.update_state("test-session", sample_ui_state)
        assert result is True
        assert "ui_state:test-session" in ui_manager._in_memory_fallback

    @pytest.mark.asyncio
    async def test_get_state_retrieves_from_memory(self, ui_manager, sample_ui_state):
        await ui_manager.update_state("test-session", sample_ui_state)
        state = await ui_manager.get_state("test-session")
        assert state["page_type"] == "transcribe_page"
        assert state["client_name"] == "John Doe"

    @pytest.mark.asyncio
    async def test_get_state_returns_empty_for_nonexistent(self, ui_manager):
        assert await ui_manager.get_state("non-existent") == {}

    @pytest.mark.asyncio
    async def test_auth_token_stored_with_state(self, ui_manager, sample_ui_state):
        await ui_manager.update_state("test-session", sample_ui_state, auth_token="bearer-token-123")
        assert ui_manager._in_memory_tokens["auth_token:test-session"] == "bearer-token-123"

    @pytest.mark.asyncio
    async def test_get_auth_token_retrieves_from_memory(self, ui_manager, sample_ui_state):
        await ui_manager.update_state("test-session", sample_ui_state, auth_token="my-token")
        assert await ui_manager.get_auth_token("test-session") == "my-token"

    @pytest.mark.asyncio
    async def test_cleanup_session_removes_data(self, ui_manager, sample_ui_state):
        await ui_manager.update_state("test-session", sample_ui_state, auth_token="token")
        await ui_manager.cleanup_session("test-session")
        assert "ui_state:test-session" not in ui_manager._in_memory_fallback
        assert "auth_token:test-session" not in ui_manager._in_memory_tokens


@pytest.mark.unit
class TestIncrementalUpdates:
    """Test incremental state update functionality."""

    @pytest.mark.asyncio
    async def test_creates_new_state_if_none_exists(self, ui_manager):
        result = await ui_manager.update_incremental(
            "new-session", {"page_type": "messages_page"}, "2026-01-23T10:00:00Z"
        )
        assert result is True
        assert (await ui_manager.get_state("new-session"))["page_type"] == "messages_page"

    @pytest.mark.asyncio
    async def test_merges_changes_preserving_originals(self, ui_manager, sample_ui_state):
        await ui_manager.update_state("test-session", sample_ui_state)
        result = await ui_manager.update_incremental(
            "test-session", {"active_tab": "documents", "documentCount": 5}, "2026-01-23T11:00:00Z"
        )
        assert result is True
        state = await ui_manager.get_state("test-session")
        assert state["active_tab"] == "documents"
        assert state["documentCount"] == 5
        assert state["page_type"] == "transcribe_page"

    @pytest.mark.asyncio
    async def test_rejects_stale_timestamp(self, ui_manager, sample_ui_state):
        # Directly set state to preserve exact timestamp
        ui_manager._in_memory_fallback["ui_state:test-session"] = json.dumps(sample_ui_state)
        result = await ui_manager.update_incremental(
            "test-session", {"active_tab": "old_value"}, "2026-01-23T09:00:00Z"
        )
        assert result is False
        assert (await ui_manager.get_state("test-session"))["active_tab"] == "transcribe"

    @pytest.mark.asyncio
    async def test_accepts_newer_timestamp(self, ui_manager, sample_ui_state):
        await ui_manager.update_state("test-session", sample_ui_state)
        result = await ui_manager.update_incremental(
            "test-session", {"active_tab": "new_value"}, "2026-01-23T12:00:00Z"
        )
        assert result is True
        assert (await ui_manager.get_state("test-session"))["active_tab"] == "new_value"


@pytest.mark.unit
class TestLoadedSessions:
    """Test loaded sessions functionality."""

    @pytest.mark.asyncio
    async def test_returns_loaded_sessions(self, ui_manager, sample_ui_state):
        await ui_manager.update_state("test-session", sample_ui_state)
        sessions = await ui_manager.get_loaded_sessions("test-session")
        assert len(sessions) == 1
        assert sessions[0]["sessionId"] == "sess-001"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_none(self, ui_manager):
        await ui_manager.update_state("test-session", {"page_type": "home"})
        assert await ui_manager.get_loaded_sessions("test-session") == []


@pytest.mark.unit
class TestCurrentClient:
    """Test current client functionality."""

    @pytest.mark.asyncio
    async def test_returns_current_client(self, ui_manager, sample_ui_state):
        await ui_manager.update_state("test-session", sample_ui_state)
        client = await ui_manager.get_current_client("test-session")
        assert client["clientId"] == "client-001"
        assert client["clientName"] == "John Doe"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_client(self, ui_manager):
        await ui_manager.update_state("test-session", {"page_type": "home"})
        assert await ui_manager.get_current_client("test-session") is None


@pytest.mark.unit
class TestSelectedTemplate:
    """Test selected template functionality."""

    @pytest.mark.asyncio
    async def test_returns_selected_template(self, ui_manager, sample_ui_state):
        await ui_manager.update_state("test-session", sample_ui_state)
        template = await ui_manager.get_selected_template("test-session")
        assert template["templateId"] == "template-001"
        assert template["templateName"] == "Session Notes"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_template(self, ui_manager):
        await ui_manager.update_state("test-session", {"page_type": "home"})
        assert await ui_manager.get_selected_template("test-session") is None


@pytest.mark.unit
class TestPageCapabilities:
    """Test page capabilities mapping."""

    @pytest.mark.asyncio
    async def test_transcribe_page_has_document_tools(self, ui_manager):
        await ui_manager.update_state("test-session", {"page_type": "transcribe_page"})
        capabilities = await ui_manager.get_page_capabilities("test-session")
        assert "search_clients" in capabilities
        assert "load_session_direct" in capabilities
        assert "generate_document_from_loaded" in capabilities

    @pytest.mark.asyncio
    async def test_messages_page_has_conversation_tools(self, ui_manager):
        await ui_manager.update_state("test-session", {"page_type": "messages_page"})
        capabilities = await ui_manager.get_page_capabilities("test-session")
        assert "get_conversations" in capabilities
        assert "get_conversation_messages" in capabilities

    @pytest.mark.asyncio
    async def test_unknown_page_has_only_base_tools(self, ui_manager):
        await ui_manager.update_state("test-session", {"page_type": "unknown_page"})
        capabilities = await ui_manager.get_page_capabilities("test-session")
        assert capabilities == ["search_clients", "get_clinic_stats", "suggest_navigation"]

    def test_sync_version_works(self, ui_manager):
        ui_manager._in_memory_fallback["ui_state:test-session"] = json.dumps({"page_type": "client_details"})
        capabilities = ui_manager.get_page_capabilities_sync("test-session")
        assert "get_client_summary" in capabilities
        assert "get_client_homework_status" in capabilities


@pytest.mark.unit
class TestSyncMethods:
    """Test sync method parity with async methods."""

    @pytest.mark.asyncio
    async def test_get_state_sync_matches_async(self, ui_manager, sample_ui_state):
        await ui_manager.update_state("test-session", sample_ui_state)
        async_state = await ui_manager.get_state("test-session")
        sync_state = ui_manager.get_state_sync("test-session")
        assert async_state["page_type"] == sync_state["page_type"]

    @pytest.mark.asyncio
    async def test_get_loaded_sessions_sync(self, ui_manager, sample_ui_state):
        await ui_manager.update_state("test-session", sample_ui_state)
        sessions = ui_manager.get_loaded_sessions_sync("test-session")
        assert len(sessions) == 1

    @pytest.mark.asyncio
    async def test_get_current_client_sync(self, ui_manager, sample_ui_state):
        await ui_manager.update_state("test-session", sample_ui_state)
        assert ui_manager.get_current_client_sync("test-session")["clientId"] == "client-001"

    @pytest.mark.asyncio
    async def test_get_auth_token_sync(self, ui_manager, sample_ui_state):
        await ui_manager.update_state("test-session", sample_ui_state, auth_token="test-token")
        assert ui_manager.get_auth_token_sync("test-session") == "test-token"


@pytest.mark.unit
class TestRedisPath:
    """Test Redis storage path with mocked clients."""

    @pytest.mark.asyncio
    async def test_update_state_uses_redis(self, initialized_ui_manager, sample_ui_state):
        initialized_ui_manager.redis_client.setex = AsyncMock()
        initialized_ui_manager.redis_client.get = AsyncMock(return_value=None)
        result = await initialized_ui_manager.update_state("test-session", sample_ui_state)
        assert result is True
        initialized_ui_manager.redis_client.setex.assert_called()

    @pytest.mark.asyncio
    async def test_get_state_uses_redis(self, initialized_ui_manager, sample_ui_state):
        initialized_ui_manager.redis_client.get = AsyncMock(return_value=json.dumps(sample_ui_state))
        state = await initialized_ui_manager.get_state("test-session")
        assert state["page_type"] == "transcribe_page"
        initialized_ui_manager.redis_client.get.assert_called_with("ui_state:test-session")

    @pytest.mark.asyncio
    async def test_cleanup_deletes_both_keys(self, initialized_ui_manager):
        initialized_ui_manager.redis_client.delete = AsyncMock()
        await initialized_ui_manager.cleanup_session("test-session")
        assert initialized_ui_manager.redis_client.delete.call_count == 2


@pytest.mark.unit
class TestProfileChangeHandling:
    """Test handling of profile changes."""

    @pytest.mark.asyncio
    async def test_clears_client_id_on_profile_change(self, ui_manager):
        await ui_manager.update_state("test-session", {
            "page_type": "transcribe_page", "profile_id": "profile-001",
            "client_id": "client-001", "client_name": "John Doe"
        })
        await ui_manager.update_state("test-session", {
            "page_type": "transcribe_page", "profile_id": "profile-002",
            "client_id": "client-001", "client_name": "John Doe"
        })
        state = await ui_manager.get_state("test-session")
        assert state.get("client_id") is None

    @pytest.mark.asyncio
    async def test_keeps_client_id_when_same_profile(self, ui_manager):
        await ui_manager.update_state("test-session", {
            "page_type": "transcribe_page", "profile_id": "profile-001",
            "client_id": "client-001", "client_name": "John Doe"
        })
        await ui_manager.update_state("test-session", {
            "page_type": "messages_page", "profile_id": "profile-001",
            "client_id": "client-001", "client_name": "John Doe"
        })
        state = await ui_manager.get_state("test-session")
        assert state.get("client_id") == "client-001"


@pytest.mark.unit
class TestErrorHandling:
    """Test error handling in state operations."""

    @pytest.mark.asyncio
    async def test_get_state_handles_invalid_json(self, ui_manager):
        ui_manager._in_memory_fallback["ui_state:bad-json"] = "not valid json {"
        assert await ui_manager.get_state("bad-json") == {}

    @pytest.mark.asyncio
    async def test_update_incremental_handles_redis_error(self, initialized_ui_manager):
        initialized_ui_manager.redis_client.get = AsyncMock(side_effect=Exception("Redis error"))
        result = await initialized_ui_manager.update_incremental(
            "test-session", {"page_type": "home"}, "2026-01-23T10:00:00Z"
        )
        assert result is False


@pytest.mark.unit
class TestSessionsSummary:
    """Test session summary functionality."""

    @pytest.mark.asyncio
    async def test_returns_summary_of_all_sessions(self, ui_manager):
        await ui_manager.update_state("session-1", {
            "page_type": "transcribe_page", "loadedSessions": [{"sessionId": "s1"}]
        })
        await ui_manager.update_state("session-2", {
            "page_type": "messages_page", "loadedSessions": []
        })
        summary = await ui_manager.get_all_sessions_summary()
        assert summary["session-1"]["page_type"] == "transcribe_page"
        assert summary["session-1"]["loaded_sessions"] == 1
        assert summary["session-2"]["page_type"] == "messages_page"

    def test_sync_version_works(self, ui_manager):
        ui_manager._in_memory_fallback["ui_state:test-1"] = json.dumps({
            "page_type": "home", "last_updated": "2026-01-23T10:00:00Z", "loadedSessions": []
        })
        assert "test-1" in ui_manager.get_all_sessions_summary_sync()
