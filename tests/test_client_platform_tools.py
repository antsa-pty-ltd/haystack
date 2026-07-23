from __future__ import annotations

import asyncio
import json
import os
import sys

from aiohttp import web
from haystack.components.tools import ToolInvoker
from haystack.dataclasses import ChatMessage, ToolCall

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import ToolManager  # noqa: E402


TASK_REF = "11111111-1111-4111-8111-111111111111"


def test_get_my_tasks_uses_client_owned_v2_route_and_minimises_output(monkeypatch):
    manager = ToolManager()
    captured = {}

    async def fake_request(method, endpoint, data=None, params=None):
        captured.update(
            {"method": method, "endpoint": endpoint, "data": data, "params": params}
        )
        return {
            "progress": {
                "completed": 1,
                "total": 2,
                "percent": 50,
                "dateLabel": "Thursday 23 July",
            },
            "tasks": [
                {
                    "id": TASK_REF,
                    "homeworkAssignId": "must-not-leak",
                    "title": "Grounding practice",
                    "description": "Practise for five minutes.",
                    "tool": "TIMER",
                    "durationLabel": "5 min",
                    "dueLabel": "Today",
                    "overdue": False,
                    "snoozedUntil": None,
                    "endDate": "2026-07-23T23:59:59.000Z",
                }
            ],
        }

    monkeypatch.setattr(manager, "_make_api_request", fake_request)
    manager.set_page_context({"timezone": "Australia/Perth"})

    result = asyncio.run(manager._get_my_tasks("this_week"))

    assert captured == {
        "method": "GET",
        "endpoint": "/api/v2/tasks/today",
        "data": None,
        "params": {"filter": "this-week", "timezone": "Australia/Perth"},
    }
    assert result["progress"]["percent"] == 50
    assert result["tasks"] == [
        {
            "task_ref": TASK_REF,
            "title": "Grounding practice",
            "description": "Practise for five minutes.",
            "task_type": "TIMER",
            "duration": "5 min",
            "due": "Today",
            "overdue": False,
            "snoozed_until": None,
        }
    ]
    assert "must-not-leak" not in str(result)


def test_get_task_details_removes_internal_assignment_and_item_ids(monkeypatch):
    manager = ToolManager()

    async def fake_request(method, endpoint, data=None, params=None):
        assert method == "GET"
        assert endpoint == f"/api/v2/tasks/{TASK_REF}"
        return {
            "id": TASK_REF,
            "homeworkAssignId": "assignment-secret",
            "title": "Evening reflection",
            "description": "A short reflection.",
            "tool": "REFLECTION",
            "toolPayload": {
                "steps": [
                    {
                        "itemId": "item-secret",
                        "prompt": "What helped today?",
                        "acceptsEmojiRating": True,
                    }
                ],
                "totalSteps": 1,
            },
            "durationLabel": None,
            "dueLabel": "Today",
            "completedAt": None,
            "assignedBy": {"name": "Dr Example", "initials": "DE"},
        }

    monkeypatch.setattr(manager, "_make_api_request", fake_request)
    result = asyncio.run(manager._get_task_details(TASK_REF))

    assert result["task"]["instructions"] == {
        "steps": [{"prompt": "What helped today?", "accepts_rating": True}],
        "total_steps": 1,
    }
    serialized = str(result)
    assert TASK_REF not in serialized
    assert "assignment-secret" not in serialized
    assert "item-secret" not in serialized


def test_get_task_details_rejects_untrusted_reference_before_api_access(monkeypatch):
    manager = ToolManager()

    async def unexpected_request(*_args, **_kwargs):
        raise AssertionError("invalid references must not reach the API")

    monkeypatch.setattr(manager, "_make_api_request", unexpected_request)
    result = asyncio.run(manager._get_task_details("../../clients"))

    assert result["status"] == "invalid_reference"


def test_record_mood_entry_requires_explicit_confirmation(monkeypatch):
    manager = ToolManager()

    async def unexpected_request(*_args, **_kwargs):
        raise AssertionError("unconfirmed mood must not be written")

    monkeypatch.setattr(manager, "_make_api_request", unexpected_request)
    result = asyncio.run(
        manager._record_mood_entry(
            feeling="anxious",
            confirmed=False,
            note="A difficult morning",
        )
    )

    assert result["saved"] is False
    assert result["requires_confirmation"] is True


def test_record_mood_entry_maps_mobile_contract_and_omits_record_id(monkeypatch):
    manager = ToolManager()
    captured = {}

    async def fake_request(method, endpoint, data=None, params=None):
        captured.update(
            {"method": method, "endpoint": endpoint, "data": data, "params": params}
        )
        return {
            "id": "mood-record-secret",
            "flag": 15,
            "point": 3,
            "comment": "Low energy after lunch",
            "activity": 1,
            "createdAt": "2026-07-23T10:00:00.000Z",
        }

    monkeypatch.setattr(manager, "_make_api_request", fake_request)
    result = asyncio.run(
        manager._record_mood_entry(
            feeling="tired",
            confirmed=True,
            note="  Low energy after lunch  ",
            activity="working",
        )
    )

    assert captured == {
        "method": "POST",
        "endpoint": "/client-mood/update",
        "data": {
            "flag": 15,
            "point": 3,
            "comment": "Low energy after lunch",
            "activity": 1,
        },
        "params": None,
    }
    assert result == {
        "saved": True,
        "data_source": "ANTSA client mood log",
        "feeling": "Tired",
        "valence": 3,
        "activity": "Working",
        "note": "Low energy after lunch",
        "recorded_at": "2026-07-23T10:00:00.000Z",
        "message": "Mood entry saved to ANTSA.",
    }
    assert "mood-record-secret" not in str(result)


def test_record_mood_entry_runs_through_haystack_worker_with_client_auth(monkeypatch):
    manager = ToolManager()
    captured = {}

    async def fake_request(method, endpoint, data=None, params=None):
        captured.update(
            {
                "auth_token": manager.auth_token,
                "profile_id": manager.profile_id,
                "method": method,
                "endpoint": endpoint,
                "data": data,
            }
        )
        return {"createdAt": "2026-07-23T10:00:00.000Z"}

    monkeypatch.setattr(manager, "_make_api_request", fake_request)
    manager.set_auth_token("client-jwt", "client-test")
    runtime_tools = manager.get_haystack_component_tools("antsabot_companion")
    invoker = ToolInvoker(tools=runtime_tools, raise_on_failure=True)

    result = invoker.run(
        messages=[
            ChatMessage.from_assistant(
                tool_calls=[
                    ToolCall(
                        tool_name="record_mood_entry",
                        arguments={
                            "feeling": "anxious",
                            "confirmed": True,
                            "note": "Before a presentation",
                        },
                    )
                ]
            )
        ]
    )

    payload = json.loads(result["tool_messages"][0].tool_call_result.result)
    assert payload["success"] is True
    assert payload["result"]["saved"] is True
    assert captured == {
        "auth_token": "client-jwt",
        "profile_id": "client-test",
        "method": "POST",
        "endpoint": "/client-mood/update",
        "data": {
            "flag": 6,
            "point": 2,
            "comment": "Before a presentation",
        },
    }


def test_api_helper_preserves_v2_path_and_accepts_created_response():
    async def exercise_request():
        observed = {}

        async def handler(request):
            observed["path"] = request.path
            observed["authorization"] = request.headers.get("Authorization")
            observed["profileid"] = request.headers.get("profileid")
            observed["body"] = await request.json()
            return web.json_response({"created": True}, status=201)

        app = web.Application()
        app.router.add_post("/api/v2/tasks/example", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]

        manager = ToolManager()
        manager.api_base_url = f"http://127.0.0.1:{port}"
        manager.set_auth_token("client-jwt", "client-test")
        try:
            result = await manager._make_api_request(
                "POST",
                "/api/v2/tasks/example",
                data={"value": 1},
            )
        finally:
            await runner.cleanup()

        return result, observed

    result, observed = asyncio.run(exercise_request())

    assert result == {"created": True}
    assert observed == {
        "path": "/api/v2/tasks/example",
        "authorization": "Bearer client-jwt",
        "profileid": None,
        "body": {"value": 1},
    }
