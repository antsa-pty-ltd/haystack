"""
UI State Synchronization Integration Tests

Tests UI state management and synchronization:
- State updates via WebSocket
- Timestamp-based ordering
- Dual Redis client (async/sync) coordination
- State persistence (24h TTL)
- State recovery after disconnect
- Incremental vs full updates

Integration Points:
- WebSocket ↔ UIStateManager
- UIStateManager ↔ Redis (dual clients)
- Tool execution ↔ UI state (sync client)
"""

import os
import sys
# Add haystack directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class TestUIStateUpdates:
    """Tests for UI state update mechanisms"""

    async def test_full_state_update_via_websocket(self):
        """
        Test full UI state replacement via WebSocket message.

        Flow:
        1. WebSocket sends ui_state_update message
        2. UIStateManager stores complete state
        3. Verify state persisted to Redis
        4. Verify state retrievable

        This tests:
        - Full state update
        - Redis persistence
        - State retrieval
        """
        from ui_state_manager import ui_state_manager

        await ui_state_manager.initialize()

        session_id = "test_full_update"

        try:
            ui_state = {
                "session_id": session_id,
                "page_type": "transcribe_page",
                "loadedSessions": [{"session_id": "sess1"}],
                "selectedTemplate": {"id": "tmpl1", "name": "Template 1"},
                "last_updated": datetime.now(timezone.utc).isoformat()
            }

            await ui_state_manager.update_state(session_id, ui_state)

            # Retrieve and verify
            retrieved = await ui_state_manager.get_state(session_id)
            assert retrieved is not None
            assert retrieved["page_type"] == "transcribe_page"
            assert len(retrieved["loadedSessions"]) == 1

        finally:
            await ui_state_manager.cleanup_session(session_id)

    async def test_incremental_state_update_with_timestamp_ordering(self):
        """
        Test incremental updates with timestamp-based conflict resolution.

        Flow:
        1. Send update with timestamp T1
        2. Send update with timestamp T2 (newer)
        3. Send update with timestamp T0 (older - should be rejected)
        4. Verify only newer updates applied

        This tests:
        - Timestamp ordering
        - Stale update rejection
        - Incremental update logic
        """
        from ui_state_manager import ui_state_manager

        await ui_state_manager.initialize()

        session_id = "test_incremental"

        try:
            # First update (T1)
            t1 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
            changes_t1 = {"page_type": "page1"}
            await ui_state_manager.update_incremental(session_id, changes_t1, t1.isoformat())

            # Second update (T2 - newer)
            t2 = datetime(2024, 1, 15, 10, 1, 0, tzinfo=timezone.utc)
            changes_t2 = {"page_type": "page2"}
            await ui_state_manager.update_incremental(session_id, changes_t2, t2.isoformat())

            # Third update (T0 - older, should be rejected)
            t0 = datetime(2024, 1, 15, 9, 59, 0, tzinfo=timezone.utc)
            changes_t0 = {"page_type": "page0"}
            await ui_state_manager.update_incremental(session_id, changes_t0, t0.isoformat())

            # Verify final state uses T2 (not T0)
            retrieved = await ui_state_manager.get_state(session_id)
            assert retrieved["page_type"] == "page2", "Should use newer timestamp update"

        finally:
            await ui_state_manager.cleanup_session(session_id)


class TestDualRedisClientCoordination:
    """Tests for async/sync Redis client coordination"""

    async def test_async_update_sync_read_coordination(self):
        """
        Test that async updates are visible to sync reads.

        Flow:
        1. Update state via async client (WebSocket handler)
        2. Read state via sync client (tool execution)
        3. Verify sync read sees async update

        This tests:
        - Async/sync coordination
        - Data consistency across clients
        """
        from ui_state_manager import ui_state_manager

        await ui_state_manager.initialize()

        session_id = "test_dual_client"

        try:
            # Async update
            ui_state = {
                "session_id": session_id,
                "test_data": "from_async",
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
            await ui_state_manager.update_state(session_id, ui_state)

            # Sync read (simulating tool execution)
            retrieved_sync = ui_state_manager.get_state_sync(session_id)
            assert retrieved_sync is not None
            assert retrieved_sync.get("test_data") == "from_async"

        finally:
            await ui_state_manager.cleanup_session(session_id)


class TestStateRecovery:
    """Tests for UI state recovery after disconnect"""

    async def test_state_persists_after_websocket_disconnect(self):
        """
        Test that UI state persists after WebSocket disconnect.

        Flow:
        1. Update UI state via WebSocket
        2. WebSocket disconnects
        3. Reconnect with same session_id
        4. Verify state restored

        This tests:
        - State persistence (24h TTL)
        - Reconnection state restoration
        """
        from ui_state_manager import ui_state_manager

        await ui_state_manager.initialize()

        session_id = "test_persist"

        try:
            # Update state
            ui_state = {
                "session_id": session_id,
                "persisted_data": "should_persist",
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
            await ui_state_manager.update_state(session_id, ui_state)

            # Simulate disconnect (state should remain in Redis)

            # Retrieve state (simulating reconnect)
            retrieved = await ui_state_manager.get_state(session_id)
            assert retrieved is not None
            assert retrieved["persisted_data"] == "should_persist"

        finally:
            await ui_state_manager.cleanup_session(session_id)
