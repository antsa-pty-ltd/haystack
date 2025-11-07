"""
Redis Failover Scenarios Integration Tests

Tests Redis connection failures and recovery:
- Session operations during Redis outage
- Fallback to in-memory storage
- Recovery when Redis comes back online
- Data consistency across failover
- Tool execution during Redis failure

Integration Points:
- SessionManager ↔ Redis
- UIStateManager ↔ Redis
- Fallback mechanisms
- Recovery procedures
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from redis.exceptions import ConnectionError as RedisConnectionError

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class TestRedisFailoverDuringOperations:
    """Tests for Redis failover during active operations"""

    async def test_session_creation_during_redis_outage(self):
        """
        Test session creation falls back to in-memory when Redis is down.

        Flow:
        1. Simulate Redis connection failure
        2. Create session (should use in-memory fallback)
        3. Verify session is accessible
        4. Verify operations continue

        This tests:
        - Automatic failover to in-memory
        - Session operations without Redis
        """
        from session_manager import session_manager

        await session_manager.initialize()

        # Mock Redis to fail
        with patch.object(session_manager, 'redis_client', None):
            # Create session without Redis
            session_id = await session_manager.create_session(
                persona_type="web_assistant",
                context={"test": "no_redis"}
            )

            # Verify session exists in local storage
            session = await session_manager.get_session(session_id)
            assert session is not None, "Session should be created in local storage"
            assert session.session_id == session_id

            # Cleanup
            await session_manager.delete_session(session_id)

    async def test_session_retrieval_redis_recovery(self):
        """
        Test session recovery when Redis comes back online.

        Flow:
        1. Create session with Redis available
        2. Simulate Redis failure
        3. Access session (from local cache)
        4. Simulate Redis recovery
        5. Verify session persists to Redis

        This tests:
        - Redis recovery handling
        - Data persistence after recovery
        """
        pytest.skip("Requires dynamic Redis connection management")

    async def test_tool_execution_during_redis_outage(self):
        """
        Test that tool execution continues during Redis outage.

        Flow:
        1. Create session
        2. Simulate Redis failure
        3. Execute tool
        4. Verify tool executes successfully (uses in-memory session)

        This tests:
        - Tool execution resilience
        - Session access fallback
        """
        from session_manager import session_manager
        from tools import tool_manager

        await session_manager.initialize()

        session_id = await session_manager.create_session(
            persona_type="web_assistant",
            auth_token="test_token",
            profile_id="test_profile"
        )

        try:
            with patch('httpx.AsyncClient') as mock_http:
                async def mock_response(*args, **kwargs):
                    response = AsyncMock()
                    response.status_code = 200
                    response.json = AsyncMock(return_value={"clients": []})
                    return response

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(side_effect=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_http.return_value = mock_client

                # Simulate Redis failure
                with patch.object(session_manager, 'redis_client', None):
                    # Execute tool
                    tool_manager.set_auth_token("test_token", "test_profile")
                    result = await tool_manager.execute_tool("search_clients", {"query": "test"}, session_id)

                    # Tool should execute despite Redis outage
                    assert result is not None

        finally:
            await session_manager.delete_session(session_id)


class TestUIStateFailover:
    """Tests for UI state manager during Redis failures"""

    async def test_ui_state_update_during_redis_outage(self):
        """
        Test UI state updates fallback to in-memory during Redis outage.
        """
        from ui_state_manager import ui_state_manager

        await ui_state_manager.initialize()

        session_id = "test_ui_failover"

        try:
            # Simulate Redis failure
            with patch.object(ui_state_manager, 'redis_client', None), \
                 patch.object(ui_state_manager, 'redis_client_sync', None):

                # Update state (should use in-memory fallback)
                ui_state = {
                    "session_id": session_id,
                    "test_key": "test_value",
                    "last_updated": "2024-01-15T10:00:00Z"
                }

                await ui_state_manager.update_state(session_id, ui_state)

                # Retrieve state (should work from memory)
                retrieved = await ui_state_manager.get_state(session_id)
                assert retrieved is not None
                assert retrieved.get("test_key") == "test_value"

        finally:
            await ui_state_manager.cleanup_session(session_id)


class TestDataConsistencyDuringFailover:
    """Tests for data consistency across Redis failover"""

    async def test_session_messages_preserved_during_outage(self):
        """
        Test that messages added during Redis outage are preserved.

        Flow:
        1. Create session with Redis
        2. Add messages
        3. Redis fails
        4. Add more messages (to in-memory)
        5. Verify all messages accessible

        This tests:
        - Message preservation
        - Data consistency
        """
        from session_manager import session_manager

        await session_manager.initialize()

        session_id = await session_manager.create_session(
            persona_type="web_assistant"
        )

        try:
            # Add messages before outage
            await session_manager.add_message(session_id, "user", "Message before outage")

            # Simulate Redis outage
            with patch.object(session_manager, 'redis_client', None):
                # Add messages during outage
                await session_manager.add_message(session_id, "assistant", "Message during outage")

            # Retrieve all messages
            messages = await session_manager.get_messages(session_id)
            assert len(messages) >= 2, "All messages should be preserved"

        finally:
            await session_manager.delete_session(session_id)
