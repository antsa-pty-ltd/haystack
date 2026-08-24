"""Bounded-memory and distributed-session regression tests."""

from __future__ import annotations

import asyncio
import json

from session_manager import SessionManager, _requires_redis as sessions_require_redis
from tools import ToolManager
from ui_state_manager import UIStateManager, _requires_redis as ui_state_requires_redis, ui_state_manager


def test_redis_backed_sessions_are_not_mirrored_into_process_memory():
    class RedisDouble:
        async def setex(self, *_args):
            return True

    async def run():
        manager = SessionManager()
        manager.redis_client = RedisDouble()
        session_id = await manager.create_session("web_assistant", profile_id="profile-a")
        assert session_id not in manager.local_sessions

    asyncio.run(run())


def test_production_disallows_process_local_session_and_ui_state(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert sessions_require_redis() is True
    assert ui_state_requires_redis() is True

    monkeypatch.setenv("ENVIRONMENT", "development")
    assert sessions_require_redis() is False
    assert ui_state_requires_redis() is False


def test_degraded_ui_state_storage_is_bounded_and_expires():
    manager = UIStateManager()
    manager.MAX_FALLBACK_ENTRIES = 2
    manager.STATE_TTL = 60
    manager._set_fallback("ui_state:a", "{}")
    manager._set_fallback("ui_state:b", "{}")
    manager._set_fallback("ui_state:c", "{}")
    assert len(manager._in_memory_expiry) == 2
    assert manager._get_fallback("ui_state:a") is None

    manager._in_memory_expiry["ui_state:b"] = 0
    assert manager._get_fallback("ui_state:b") is None


def test_tools_never_scan_or_read_another_ui_session():
    """A transcript ID from another active browser session stays invisible."""
    manager = ToolManager()
    previous_initialized = ui_state_manager._initialized
    ui_state_manager._initialized = False
    keys = ["ui_state:ui-a", "ui_state:ui-b"]
    try:
        ui_state_manager._set_fallback(
            keys[0],
            json.dumps(
                {
                    "page_type": "transcribe_page",
                    "loadedSessions": [
                        {"sessionId": "transcript-a", "content": "tenant A clinical content"}
                    ],
                }
            ),
        )
        ui_state_manager._set_fallback(
            keys[1],
            json.dumps(
                {
                    "page_type": "transcribe_page",
                    "loadedSessions": [
                        {"sessionId": "transcript-b", "content": "tenant B clinical content"}
                    ],
                }
            ),
        )

        async def run():
            own = await manager.execute_tool(
                "get_session_content",
                {"session_id": "transcript-a"},
                ui_session_id="ui-a",
            )
            foreign = await manager.execute_tool(
                "get_session_content",
                {"session_id": "transcript-b"},
                ui_session_id="ui-a",
            )
            return own, foreign

        own, foreign = asyncio.run(run())
        assert own["success"] is True
        assert own["result"]["content"] == "tenant A clinical content"
        assert foreign["success"] is True
        assert foreign["result"]["status"] == "session_not_found"
        assert "tenant B clinical content" not in json.dumps(foreign)
    finally:
        for key in keys:
            ui_state_manager._in_memory_fallback.pop(key, None)
            ui_state_manager._in_memory_expiry.pop(key, None)
        ui_state_manager._initialized = previous_initialized
