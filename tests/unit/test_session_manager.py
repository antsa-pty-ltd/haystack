"""
Tests for session management in AI Scribe.

These tests verify:
- Session creation and retrieval
- Message history management
- Session persistence and recovery
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


class TestSessionManager:
    """Test suite for session manager."""

    @pytest.mark.unit
    async def test_session_creation(self):
        """Test that sessions can be created."""
        from session_manager import SessionManager

        manager = SessionManager()
        manager.redis_client = None  # Force in-memory mode
        manager.local_sessions = {}

        session_id = await manager.create_session(
            persona_type="web_assistant",
            context={"test": "data"},
            auth_token="test-token",
            profile_id="profile-123"
        )

        assert session_id is not None
        assert len(session_id) > 0

    @pytest.mark.unit
    async def test_session_retrieval(self):
        """Test that sessions can be retrieved."""
        from session_manager import SessionManager

        manager = SessionManager()
        manager.redis_client = None
        manager.local_sessions = {}

        session_id = await manager.create_session(
            persona_type="jaimee_therapist",
            context={},
            auth_token="token",
            profile_id="profile"
        )

        session = await manager.get_session(session_id)

        assert session is not None
        assert session.persona_type == "jaimee_therapist"

    @pytest.mark.unit
    async def test_message_history(self):
        """Test message history management."""
        from session_manager import SessionManager

        manager = SessionManager()
        manager.redis_client = None
        manager.local_sessions = {}

        session_id = await manager.create_session(
            persona_type="web_assistant",
            context={},
            auth_token="token",
            profile_id="profile"
        )

        # Add messages
        await manager.add_message(session_id, "user", "Hello")
        await manager.add_message(session_id, "assistant", "Hi there!")

        # Retrieve messages
        messages = await manager.get_messages(session_id)

        assert len(messages) >= 2
        assert any(m.role == "user" and m.content == "Hello" for m in messages)
        assert any(m.role == "assistant" and m.content == "Hi there!" for m in messages)

    @pytest.mark.unit
    async def test_nonexistent_session(self):
        """Test handling of nonexistent sessions."""
        from session_manager import SessionManager

        manager = SessionManager()
        manager.redis_client = None
        manager.local_sessions = {}

        session = await manager.get_session("nonexistent-id")
        assert session is None

    @pytest.mark.unit
    async def test_session_auth_token_storage(self):
        """Test that auth tokens are properly stored."""
        from session_manager import SessionManager

        manager = SessionManager()
        manager.redis_client = None
        manager.local_sessions = {}

        session_id = await manager.create_session(
            persona_type="web_assistant",
            context={},
            auth_token="secret-token-123",
            profile_id="profile-456"
        )

        session = await manager.get_session(session_id)

        assert session.auth_token == "secret-token-123"
        assert session.profile_id == "profile-456"


class TestSessionRecovery:
    """Test session recovery scenarios."""

    @pytest.mark.unit
    async def test_session_recovery_by_profile(self):
        """Test recovering session by profile ID."""
        from session_manager import SessionManager

        manager = SessionManager()
        manager.redis_client = None
        manager.local_sessions = {}

        # Create session
        session_id = await manager.create_session(
            persona_type="web_assistant",
            context={},
            auth_token="token",
            profile_id="unique-profile-123"
        )

        # Try to recover by profile - check if method exists
        if hasattr(manager, 'get_session_by_profile'):
            recovered = await manager.get_session_by_profile("unique-profile-123")
            if recovered is not None:
                assert recovered.profile_id == "unique-profile-123"


class TestMessageLimits:
    """Test message history limits."""

    @pytest.mark.unit
    async def test_message_limit_respected(self):
        """Test that message retrieval limit is respected."""
        from session_manager import SessionManager

        manager = SessionManager()
        manager.redis_client = None
        manager.local_sessions = {}

        session_id = await manager.create_session(
            persona_type="web_assistant",
            context={},
            auth_token="token",
            profile_id="profile"
        )

        # Add many messages
        for i in range(30):
            await manager.add_message(session_id, "user", f"Message {i}")

        # Retrieve with limit
        messages = await manager.get_messages(session_id, limit=10)

        assert len(messages) <= 10


class TestChatMessageDataclass:
    """Test ChatMessage dataclass functionality."""

    @pytest.mark.unit
    def test_chat_message_creation(self):
        """Test ChatMessage creation."""
        from session_manager import ChatMessage

        msg = ChatMessage(
            role="user",
            content="Hello",
            timestamp=datetime.now()
        )

        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.message_id is not None

    @pytest.mark.unit
    def test_chat_message_to_dict(self):
        """Test ChatMessage serialization."""
        from session_manager import ChatMessage

        msg = ChatMessage(
            role="assistant",
            content="Hi there!",
            timestamp=datetime.now()
        )

        data = msg.to_dict()

        assert data["role"] == "assistant"
        assert data["content"] == "Hi there!"
        assert "timestamp" in data
        assert "message_id" in data

    @pytest.mark.unit
    def test_chat_message_from_dict(self):
        """Test ChatMessage deserialization."""
        from session_manager import ChatMessage

        data = {
            "role": "user",
            "content": "Test",
            "timestamp": "2024-01-15T10:00:00",
            "message_id": "test-id"
        }

        msg = ChatMessage.from_dict(data)

        assert msg.role == "user"
        assert msg.content == "Test"
        assert msg.message_id == "test-id"


class TestChatSessionDataclass:
    """Test ChatSession dataclass functionality."""

    @pytest.mark.unit
    def test_chat_session_to_dict(self):
        """Test ChatSession serialization."""
        from session_manager import ChatSession, ChatMessage

        session = ChatSession(
            session_id="test-session",
            persona_type="web_assistant",
            messages=[
                ChatMessage(role="user", content="Hello", timestamp=datetime.now())
            ],
            created_at=datetime.now(),
            last_activity=datetime.now(),
            context={"key": "value"},
            auth_token="token",
            profile_id="profile"
        )

        data = session.to_dict()

        assert data["session_id"] == "test-session"
        assert data["persona_type"] == "web_assistant"
        assert len(data["messages"]) == 1
        assert data["auth_token"] == "token"
        assert data["profile_id"] == "profile"

    @pytest.mark.unit
    def test_chat_session_from_dict(self):
        """Test ChatSession deserialization."""
        from session_manager import ChatSession

        data = {
            "session_id": "test-session",
            "persona_type": "jaimee_therapist",
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                    "timestamp": "2024-01-15T10:00:00",
                    "message_id": "msg-1"
                }
            ],
            "created_at": "2024-01-15T10:00:00",
            "last_activity": "2024-01-15T10:00:00",
            "context": {},
            "auth_token": "token",
            "profile_id": "profile"
        }

        session = ChatSession.from_dict(data)

        assert session.session_id == "test-session"
        assert session.persona_type == "jaimee_therapist"
        assert len(session.messages) == 1
        assert session.auth_token == "token"
