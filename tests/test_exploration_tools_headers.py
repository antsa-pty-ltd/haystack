"""
Unit tests proving the doc-gen agent now forwards BOTH `Authorization` and
`profileid` headers on every API tool callback.

Background. Pre-fix, the agent only forwarded `Authorization`. The API's
`ExtractProfileMiddleware` only populates `req.profile` when the `profileid`
header is present; without it, the API's tenancy filter
(`filterAccessibleTranscriptIds`) received `undefined` for the profile id,
short-circuited to `[]`, and the agent collected zero segments. End-user
symptom: empty document body. Reported 2026-05-24.

This test mocks `httpx.AsyncClient` and asserts the exact headers each agent
tool sends. If a future change drops `profileid` again, this test fails.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Make repo importable when run from anywhere.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.exploration_tools import (  # noqa: E402
    ExplorationContext,
    _api_headers,
    get_exploration_context,
    peek_session,
    pull_full_session,
    reset_exploration_context,
    search_session,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolated_context():
    """Reset the module-global context before each test."""
    reset_exploration_context(
        authorization="Bearer eyJ.test.jwt",
        generation_id="gen-1",
        profileid="profile-uuid-abc",
    )
    yield
    reset_exploration_context()


class _CapturingClient:
    """Minimal stand-in for `httpx.AsyncClient` that captures the headers."""

    captured: List[Dict[str, Any]] = []

    def __init__(self, *_args, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        pass

    async def post(self, url, json=None, headers=None, **_kwargs):
        type(self).captured.append({"url": url, "json": json, "headers": headers or {}})
        resp = MagicMock()
        resp.status_code = 200
        resp.json = MagicMock(return_value={"segments": []})
        resp.raise_for_status = MagicMock()
        return resp


@pytest.fixture
def capture_http():
    _CapturingClient.captured = []
    with patch("agents.exploration_tools.httpx.AsyncClient", _CapturingClient):
        yield _CapturingClient


# ── _api_headers (the building block) ─────────────────────────────────────


class TestApiHeaders:
    def test_includes_both_headers_when_context_has_both(self):
        ctx = ExplorationContext()
        ctx.authorization = "Bearer xyz"
        ctx.profileid = "prof-1"
        headers = _api_headers(ctx)
        assert headers == {"Authorization": "Bearer xyz", "profileid": "prof-1"}

    def test_omits_profileid_when_unset(self):
        ctx = ExplorationContext()
        ctx.authorization = "Bearer xyz"
        # profileid intentionally left None
        headers = _api_headers(ctx)
        assert headers == {"Authorization": "Bearer xyz"}

    def test_omits_authorization_when_unset(self):
        ctx = ExplorationContext()
        ctx.profileid = "prof-1"
        headers = _api_headers(ctx)
        assert headers == {"profileid": "prof-1"}

    def test_returns_empty_dict_when_both_unset(self):
        assert _api_headers(ExplorationContext()) == {}


# ── reset_exploration_context wires profileid through ─────────────────────


class TestResetExplorationContext:
    def test_persists_profileid_on_the_context(self):
        reset_exploration_context(
            authorization="Bearer abc",
            generation_id="gen-1",
            profileid="prof-xyz",
        )
        ctx = get_exploration_context()
        assert ctx.authorization == "Bearer abc"
        assert ctx.profileid == "prof-xyz"
        assert ctx.generation_id == "gen-1"

    def test_defaults_profileid_to_none_for_legacy_callers(self):
        reset_exploration_context(authorization="Bearer abc", generation_id="gen-1")
        ctx = get_exploration_context()
        assert ctx.profileid is None


# ── Each agent tool forwards both headers on its API callback ─────────────


def _run(coro):
    return asyncio.run(coro)


class TestPullFullSessionForwardsProfileid:
    def test_includes_authorization_and_profileid_in_outbound_headers(self, capture_http):
        _run(pull_full_session("session-1"))
        assert len(capture_http.captured) == 1, "expected exactly one outbound call"
        call = capture_http.captured[0]
        assert "/ai/transcripts/segments-by-sessions" in call["url"]
        assert call["headers"].get("Authorization") == "Bearer eyJ.test.jwt"
        assert call["headers"].get("profileid") == "profile-uuid-abc"


class TestPeekSessionForwardsProfileid:
    def test_includes_authorization_and_profileid_in_outbound_headers(self, capture_http):
        _run(peek_session("session-1"))
        assert len(capture_http.captured) == 1
        call = capture_http.captured[0]
        assert "/ai/transcripts/segments-by-sessions" in call["url"]
        assert call["headers"].get("Authorization") == "Bearer eyJ.test.jwt"
        assert call["headers"].get("profileid") == "profile-uuid-abc"


class TestSearchSessionForwardsProfileid:
    def test_includes_authorization_and_profileid_in_outbound_headers(self, capture_http):
        _run(search_session("session-1", query="topic"))
        assert len(capture_http.captured) == 1
        call = capture_http.captured[0]
        assert "/ai/semantic-search" in call["url"]
        assert call["headers"].get("Authorization") == "Bearer eyJ.test.jwt"
        assert call["headers"].get("profileid") == "profile-uuid-abc"


class TestRegressionGuardLegacyAuthOnlyHeader:
    """
    Regression guard: the pre-fix behaviour sent only `{"Authorization":
    ...}` -- if a future refactor accidentally restores that shape, these
    assertions will catch it.
    """

    def test_no_tool_call_omits_profileid_when_context_has_one(self, capture_http):
        _run(pull_full_session("s1"))
        _run(peek_session("s2"))
        _run(search_session("s3", query="x"))
        assert len(capture_http.captured) == 3
        for call in capture_http.captured:
            assert "profileid" in call["headers"], (
                f"call to {call['url']} omitted profileid -- regression of the "
                f"empty-content doc-gen bug (2026-05-24)"
            )
