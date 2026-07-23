from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import ToolManager  # noqa: E402


def test_psychoeducation_tool_calls_authenticated_agent_search_and_bounds_results(monkeypatch):
    manager = ToolManager()
    captured = {}

    async def fake_request(method, endpoint, data=None, params=None):
        captured.update(
            {"method": method, "endpoint": endpoint, "data": data, "params": params}
        )
        return {
            "retrieval": "hybrid",
            "matches": [
                {
                    "title": "Understanding panic",
                    "topic": "Anxiety",
                    "authorName": "ANTSA Clinical Team",
                    "type": "ARTICLE",
                    "passages": ["First passage", "Second passage", "Unbounded third"],
                    "id": "must-not-leak",
                }
            ],
        }

    monkeypatch.setattr(manager, "_make_api_request", fake_request)
    result = asyncio.run(
        manager._search_psychoeducation("  panic and grounding  ", max_results=99)
    )

    assert captured == {
        "method": "GET",
        "endpoint": "/psychoeducation/agent-search",
        "data": None,
        "params": {"query": "panic and grounding", "limit": 5},
    }
    assert result["retrieval"] == "hybrid"
    assert result["matches"] == [
        {
            "title": "Understanding panic",
            "topic": "Anxiety",
            "author_name": "ANTSA Clinical Team",
            "resource_type": "ARTICLE",
            "passages": ["First passage", "Second passage"],
        }
    ]
    assert "must-not-leak" not in str(result)


def test_psychoeducation_tool_fails_closed_without_fabricating_content(monkeypatch):
    manager = ToolManager()

    async def unavailable(*_args, **_kwargs):
        raise RuntimeError("temporary backend failure")

    monkeypatch.setattr(manager, "_make_api_request", unavailable)
    result = asyncio.run(manager._search_psychoeducation("sleep"))

    assert result["retrieval"] == "unavailable"
    assert result["matches"] == []
    assert "temporarily unavailable" in result["message"]


def test_psychoeducation_tool_rejects_invalid_queries_before_api_access(monkeypatch):
    manager = ToolManager()

    async def unexpected_request(*_args, **_kwargs):
        raise AssertionError("must not call API")

    monkeypatch.setattr(manager, "_make_api_request", unexpected_request)

    result = asyncio.run(manager._search_psychoeducation(None))

    assert result["retrieval"] == "none"
    assert result["matches"] == []


def test_client_profile_tool_omits_direct_identifiers_and_contact_details(monkeypatch):
    manager = ToolManager()

    async def fake_request(*_args, **_kwargs):
        return {
            "id": "account-secret-id",
            "email": "client@example.com",
            "role": "CLIENT",
            "status": "ACTIVE",
            "profiles": [],
            "client": {
                "firstName": "Private",
                "lastName": "Person",
                "dob": "1990-01-01T00:00:00.000Z",
                "phone": "+61400000000",
                "gender": "non-binary",
                "occupation": "teacher",
            },
        }

    monkeypatch.setattr(manager, "_make_api_request", fake_request)
    result = asyncio.run(manager._get_user_profile())
    serialized = str(result)

    assert result["profile"]["age"] >= 0
    assert result["profile"]["gender"] == "non-binary"
    assert result["profile"]["occupation"] == "teacher"
    for sensitive in (
        "Private",
        "Person",
        "client@example.com",
        "+61400000000",
        "1990-01-01",
        "account-secret-id",
    ):
        assert sensitive not in serialized
