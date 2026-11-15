"""
Regression tests for the practitioner (web_assistant) tools.

Each test pins a defect that was reproduced against the live API during the
November 2026 ANTSAbot tool audit:

- get_practitioner_today computed "today" in UTC and queried the API with a
  bare date, so morning sessions vanished, tomorrow's first session was counted
  as today, and "next session" skipped everything still ahead today.
- Unread messages were read from a route that does not exist, so the tool
  always reported zero.
- search_sessions exposed two ids per session; follow-up tools need the
  transcript id, and the model frequently passed the other one.
- semantic_search_sessions called a helper that does not exist and omitted the
  client id the API requires.
- get_client_base asked for more rows than the API allows and always failed.
- get_templates returned every template body (100 KB+ per call).
- set_selected_template / generate_document_from_loaded required the model to
  echo a whole template body.
- An unexpected argument from the model crashed the call with a TypeError.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import tools as tools_module  # noqa: E402
from tools import tool_manager  # noqa: E402

SYDNEY = ZoneInfo("Australia/Sydney")
CLIENT_ID = "82dd0e7f-2f92-4cca-a36a-ed12dc688eff"


class FakeApi:
    """Records requests and replays canned responses keyed by path prefix."""

    def __init__(self, routes: Dict[str, Any]):
        self.routes = routes
        self.calls: List[Tuple[str, str, Optional[Dict], Optional[Dict]]] = []

    async def __call__(self, method, endpoint, data=None, params=None):
        path = endpoint.lstrip("/")
        self.calls.append((method, path, data, params))
        for prefix, response in self.routes.items():
            if path.startswith(prefix):
                if isinstance(response, Exception):
                    raise response
                if callable(response):
                    return response(method, path, data, params)
                return response
        raise Exception(f"API request failed: 404 - no fake route for {path}")

    def calls_to(self, prefix: str):
        return [c for c in self.calls if c[1].startswith(prefix)]


@pytest.fixture
def api(monkeypatch):
    def install(routes: Dict[str, Any]) -> FakeApi:
        fake = FakeApi(routes)
        monkeypatch.setattr(tool_manager, "_make_api_request", fake)
        return fake

    tool_manager.set_page_context({"timezone": "Australia/Sydney"})
    return install


def freeze_now(monkeypatch, local: datetime) -> None:
    """Freeze datetime.now() inside tools.py at a Sydney-local instant."""
    instant = local.replace(tzinfo=SYDNEY)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

    monkeypatch.setattr(tools_module, "datetime", FrozenDateTime)


def session(start_utc: str, end_utc: str, status: str = "scheduled", kind: str = "video", name=("Sam", "Taylor")):
    return {
        "id": f"vs-{start_utc}",
        "clientId": CLIENT_ID,
        "scheduledStartTime": start_utc,
        "scheduledEndTime": end_utc,
        "status": status,
        "sessionType": kind,
        "client": {"id": CLIENT_ID, "firstName": name[0], "lastName": name[1]},
    }


def run(coro):
    return asyncio.run(coro)


# ── get_practitioner_today ────────────────────────────────────────────────


def test_today_uses_local_day_and_keeps_morning_sessions(api, monkeypatch):
    # 8:15am Monday in Sydney is still Sunday 21:15 UTC.
    freeze_now(monkeypatch, datetime(2026, 11, 16, 8, 15))
    fake = api({
        "video-sessions/practitioner": [
            session("2026-11-15T22:00:00.000Z", "2026-11-15T22:50:00.000Z"),  # Mon 9:00am
            session("2026-11-16T03:00:00.000Z", "2026-11-16T03:50:00.000Z", kind="telephone"),  # Mon 2:00pm
            session("2026-11-16T22:00:00.000Z", "2026-11-16T22:50:00.000Z"),  # Tue 9:00am
        ],
        "chat/rooms": {"data": []},
    })

    result = run(tool_manager._get_practitioner_today())

    assert result["status"] == "success"
    assert result["today"] == "2026-11-16"
    assert result["todayLabel"] == "Monday 16 November"
    assert [s["startLabel"] for s in result["sessionsToday"]] == ["9:00 am", "2:00 pm"]
    assert result["todayCount"] == 2
    assert result["nextSession"]["startLabel"] == "9:00 am"
    assert result["nextSession"]["dayLabel"] == "today"
    assert result["nextSession"]["startsInMinutes"] == 45
    assert result["sessionsToday"][1]["sessionTypeLabel"] == "phone call"

    # The window must start at LOCAL midnight expressed as a UTC instant, not a
    # bare date (which the API reads as UTC midnight = 11am Sydney).
    _, _, _, params = fake.calls_to("video-sessions/practitioner")[0]
    assert params["startDate"] == "2026-11-15T13:00:00.000Z"
    assert params["endDate"] == "2026-11-23T13:00:00.000Z"


def test_today_reports_breaks_progress_and_excludes_cancelled(api, monkeypatch):
    freeze_now(monkeypatch, datetime(2026, 11, 16, 14, 20))
    api({
        "video-sessions/practitioner": [
            session("2026-11-15T22:00:00.000Z", "2026-11-15T22:50:00.000Z", status="completed"),  # 9:00
            session("2026-11-16T00:00:00.000Z", "2026-11-16T00:50:00.000Z", status="cancelled"),  # 11:00
            session("2026-11-16T03:00:00.000Z", "2026-11-16T03:50:00.000Z"),  # 2:00 (in progress)
            session("2026-11-16T04:30:00.000Z", "2026-11-16T05:20:00.000Z"),  # 3:30
            session("2026-11-16T05:20:00.000Z", "2026-11-16T06:10:00.000Z"),  # 4:20 back-to-back
        ],
        "chat/rooms": {"data": []},
    })

    result = run(tool_manager._get_practitioner_today())

    assert result["todayCount"] == 4
    assert result["completedCount"] == 1
    assert result["remainingCount"] == 3
    assert [s["startLabel"] for s in result["cancelledToday"]] == ["11:00 am"]
    assert [s["timing"] for s in result["sessionsToday"]] == ["completed", "in_progress", "upcoming", "upcoming"]
    # Gaps: 9:50→2:00 (already passed) and 2:50→3:30. No break for back-to-back.
    assert [(b["startLabel"], b["endLabel"], b["minutes"]) for b in result["breaks"]] == [
        ("9:50 am", "2:00 pm", 250),
        ("2:50 pm", "3:30 pm", 40),
    ]
    assert result["breaks"][0]["alreadyPassed"] is True
    assert result["breaks"][1]["alreadyPassed"] is False
    assert result["nextSession"]["startLabel"] == "3:30 pm"


def test_today_counts_unread_from_chat_rooms(api, monkeypatch):
    freeze_now(monkeypatch, datetime(2026, 11, 16, 9, 0))
    fake = api({
        "video-sessions/practitioner": [],
        "chat/rooms": {"data": [
            {"id": "r1", "lastMessage": {"createdAt": "2026-11-15T20:00:00.000Z"}, "userRooms": [
                {"totalUnreadMessages": 3, "profile": {"id": "p"}},
                {"totalUnreadMessages": 0, "client": {"firstName": "Sam", "lastName": "Taylor"}},
            ]},
            {"id": "r2", "userRooms": [
                {"totalUnreadMessages": 0, "profile": {"id": "p"}},
                {"totalUnreadMessages": 5, "client": {"firstName": "Alex", "lastName": "Ng"}},
            ]},
        ]},
    })

    result = run(tool_manager._get_practitioner_today())

    assert fake.calls_to("chat/rooms"), "unread messages must come from chat/rooms"
    assert not fake.calls_to("messages/rooms")
    # Only the practitioner's own unread counter counts.
    assert result["unreadMessages"] == 3
    assert result["unreadRooms"] == [
        {"clientName": "Sam Taylor", "unread": 3, "lastMessageAt": "2026-11-15T20:00:00.000Z"}
    ]


def test_today_never_reports_an_empty_day_when_schedule_fails(api, monkeypatch):
    freeze_now(monkeypatch, datetime(2026, 11, 16, 9, 0))
    api({
        "video-sessions/practitioner": Exception("API request failed: 503"),
        "chat/rooms": {"data": []},
    })

    result = run(tool_manager._get_practitioner_today())

    assert result["scheduleUnavailable"] is True
    assert "Do not say the day is empty" in result["scheduleNote"]


def test_timezone_falls_back_to_country_default_not_utc(monkeypatch):
    tool_manager.set_page_context({})
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.delenv("TIMEZONE", raising=False)
    monkeypatch.setenv("COUNTRY_CODE", "AU")
    assert tool_manager._resolve_timezone()[1] == "Australia/Sydney"
    # Browser timezone wins over the deployment default; garbage is ignored.
    tool_manager.set_page_context({"timezone": "Australia/Perth"})
    assert tool_manager._resolve_timezone()[1] == "Australia/Perth"
    assert tool_manager._resolve_timezone("Not/AZone")[1] == "Australia/Perth"


# ── sessions ──────────────────────────────────────────────────────────────


def test_search_sessions_exposes_single_transcript_keyed_session_id(api):
    api({"haystack/search-sessions": {"total": 1, "sessions": [{
        "id": "transcript-id", "sessionId": "recording-id", "clientId": CLIENT_ID,
        "clientName": "Sam Taylor", "recordingDate": "2026-11-14T05:57:05.345Z",
        "duration": 6, "totalSegments": 1, "averageConfidence": 0.98,
    }]}})

    result = run(tool_manager._search_sessions(client_id=CLIENT_ID))

    row = result["sessions"][0]
    assert row["session_id"] == "transcript-id"
    assert "recording-id" not in json.dumps(result)
    assert row["client_id"] == CLIENT_ID
    assert row["recording_date_label"] == "Saturday 14 November 2026, 4:57 pm"


def test_semantic_search_sends_client_id_through_authenticated_api_helper(api):
    fake = api({"ai/semantic-search": {"segments": [{"text": "sleep has been rough"}]}})

    result = run(tool_manager._semantic_search_sessions(
        query="sleep problems", transcript_ids=["t1", "t2"], client_id=CLIENT_ID,
    ))

    assert result["status"] == "success"
    assert result["results_count"] == 1
    method, path, body, _ = fake.calls_to("ai/semantic-search")[0]
    assert method == "POST"
    assert body["clientId"] == CLIENT_ID
    assert body["transcript_ids"] == ["t1", "t2"]


def test_semantic_search_retries_once_with_looser_threshold(api):
    seen: List[float] = []

    def respond(method, path, body, params):
        seen.append(body["similarity_threshold"])
        return {"segments": [] if body["similarity_threshold"] > 0.3 else [{"text": "match"}]}

    api({"ai/semantic-search": respond})

    result = run(tool_manager._semantic_search_sessions(
        query="investors", transcript_ids=["t1"], client_id=CLIENT_ID,
    ))

    assert seen == [0.45, 0.3]
    assert result["threshold_relaxed"] is True
    assert result["results_count"] == 1


# ── clients ───────────────────────────────────────────────────────────────


def test_client_base_pages_the_roster_and_never_exceeds_api_limits(api):
    def roster(method, path, body, params):
        assert params["size"] <= 50
        page = params["page"]
        rows = [
            {"clientId": f"c{page}-{i}", "firstName": "Client", "lastName": f"{page}-{i}",
             "email": f"c{page}{i}@example.com", "statusConvert": "ACTIVE"}
            for i in range(50 if page == 1 else 10)
        ]
        return {"data": rows, "totalPage": 2, "totalRecord": 60,
                "statusCounts": {"active": 60, "pending": 0, "discharged": 0}}

    fake = api({"practitioners/clients": roster})

    result = run(tool_manager._get_client_base(limit=100))

    assert result["success"] is True
    assert result["summary"]["total_returned"] == 60
    assert result["summary"]["total_in_system"] == 60
    assert result["client_base"][0]["email"] == "c10@example.com"
    assert len(fake.calls_to("practitioners/clients")) == 2
    assert not [c for c in fake.calls if c[1].startswith("clients/")], "no per-client lookups"


def test_client_base_falls_back_for_owner_role_within_search_limit(api):
    fake = api({
        "practitioners/clients": Exception("API request failed: 403"),
        "haystack/search-clients": {"total": 1, "clients": [
            {"client_id": CLIENT_ID, "name": "Sam Taylor", "status": "ACTIVE"}]},
    })

    result = run(tool_manager._get_client_base(limit=500))

    assert result["success"] is True
    assert result["client_base"][0]["name"] == "Sam Taylor"
    assert fake.calls_to("haystack/search-clients")[0][3]["limit"] == 50
    assert "note" in result


def test_search_clients_clamps_limit_to_api_maximum(api):
    fake = api({"haystack/search-clients": {"clients": []}})
    run(tool_manager._search_clients(query="sam", limit=500))
    assert fake.calls_to("haystack/search-clients")[0][3]["limit"] == 50


def test_list_practitioners_is_honest_about_scope_for_non_owners(api):
    tool_manager.profile_id = "p1"
    api({"account/v2/me": {"email": "j@example.com", "profiles": [
        {"id": "p1", "firstName": "Jordan", "lastName": "Lee", "role": "PRACTITIONER", "status": "ACTIVE"}]}})

    result = run(tool_manager._list_practitioners())

    assert result["scope"] == "own_profile_only"
    assert result["count"] == 1
    assert "Do not present this as the complete list" in result["note"]


def test_clinic_profile_does_not_leak_raw_account_payload(api):
    tool_manager.profile_id = "p1"
    api({"account/v2/me": {"email": "j@example.com", "profiles": [
        {"id": "p1", "firstName": "Jordan", "clinic": {"id": "c1", "name": "Demo"}}]}})
    result = run(tool_manager._get_clinic_profile())
    assert result["name"] == "Demo"
    assert "raw" not in result


# ── templates ─────────────────────────────────────────────────────────────

BIG_BODY = "CRITICAL INSTRUCTIONS FOR AI ASSISTANT:\n- NEVER diagnose\n\nSOAP Notes\n" + ("Subjective: ...\n" * 2000)
TEMPLATES = [
    {"id": "t-soap", "name": "SOAP Notes", "description": "Standard", "content": BIG_BODY, "tags": ["SOAP"]},
    {"id": "t-prog", "name": "Progress Report", "description": "MSE & Risk", "content": "Progress body", "tags": []},
]


def template_routes():
    def one(method, path, body, params):
        template_id = path.split("/", 1)[1]
        for t in TEMPLATES:
            if t["id"] == template_id:
                return t
        raise Exception("API request failed: 404")

    return {"templates/": one, "templates": TEMPLATES}


def test_get_templates_returns_previews_not_bodies(api):
    api(template_routes())

    result = run(tool_manager._get_templates())

    assert result["count"] == 2
    payload = json.dumps(result)
    assert len(payload) < 2500, "listing must stay small enough for the model context"
    soap = result["templates"][0]
    assert "content" not in soap
    assert soap["content_length"] == len(BIG_BODY)
    assert soap["content_preview"].startswith("SOAP Notes"), "preview skips the injected safety preamble"


def test_get_templates_search_filters_by_name(api):
    api(template_routes())
    result = run(tool_manager._get_templates(search_query="progress"))
    assert [t["name"] for t in result["templates"]] == ["Progress Report"]


def test_set_selected_template_resolves_body_from_id(api):
    api(template_routes())

    result = run(tool_manager._set_selected_template(template_id="t-soap"))

    assert result["status"] == "ui_action_requested"
    payload = result["ui_action"]["payload"]
    assert payload["templateName"] == "SOAP Notes"
    assert payload["templateContent"] == BIG_BODY


def test_set_selected_template_rejects_unknown_id(api):
    api(template_routes())
    result = run(tool_manager._set_selected_template(template_id="missing"))
    assert result["status"] == "error"
    assert "ui_action" not in result


def test_select_template_by_name_matches_words_in_any_order(api):
    api(template_routes())
    result = run(tool_manager._select_template_by_name(template_name="notes soap"))
    assert result["ui_action"]["payload"]["templateId"] == "t-soap"


def test_generate_document_uses_saved_template_without_echoed_body(api):
    api(template_routes())

    result = run(tool_manager._generate_document_from_loaded(
        template_id="t-prog",
        sessions=[{"session_id": "s1", "client_id": CLIENT_ID, "client_name": "Sam Taylor"}],
    ))

    assert result["status"] == "ui_action_requested"
    payload = result["ui_action"]["payload"]
    assert payload["templateContent"].endswith("Progress body")
    assert payload["templateName"] == "Progress Report"


# ── execution robustness ──────────────────────────────────────────────────


def test_execute_tool_ignores_unexpected_arguments(api):
    api({"haystack/search-clients": {"clients": [{"client_id": CLIENT_ID, "name": "Sam Taylor"}]}})

    result = run(tool_manager.execute_tool(
        "search_clients", {"query": "sam", "page_context": {"x": 1}, "limit": None},
    ))

    assert result["success"] is True
    assert result["result"][0]["name"] == "Sam Taylor"


def test_execute_tool_reports_missing_required_arguments_clearly():
    result = run(tool_manager.execute_tool("get_client_summary", {}))
    assert result["success"] is False
    assert "client_id" in result["error"]


def test_load_session_direct_needs_only_identifying_fields():
    result = run(tool_manager.execute_tool(
        "load_session_direct",
        {"session_id": "t1", "client_id": CLIENT_ID, "client_name": "Sam Taylor"},
    ))
    assert result["success"] is True
    assert result["result"]["ui_action"]["payload"]["sessionId"] == "t1"


def test_tool_schemas_match_what_the_api_accepts():
    definitions = {
        t["function"]["name"]: t["function"]["parameters"]
        for t in tool_manager.get_tools_for_persona("web_assistant")
    }
    assert definitions["set_selected_template"]["required"] == ["template_id"]
    assert definitions["generate_document_from_loaded"]["required"] == []
    assert "client_id" in definitions["semantic_search_sessions"]["required"]
    assert definitions["load_session_direct"]["required"] == ["session_id", "client_id", "client_name"]


# ── pipeline helpers & persona voice ──────────────────────────────────────


def test_ui_action_payloads_are_slimmed_before_returning_to_the_model():
    from haystack.dataclasses import ChatMessage, ToolCall
    from haystack_pipeline import slim_ui_action_tool_messages

    origin = ToolCall(tool_name="set_selected_template", arguments={}, id="call-1")
    bulky = json.dumps({"success": True, "result": {
        "status": "ui_action_requested",
        "ui_action": {"type": "set_selected_template", "payload": {"templateContent": "x" * 50000}},
    }})
    plain = ChatMessage.from_tool(tool_result=json.dumps({"success": True, "result": {"total": 1}}), origin=origin)

    slimmed = slim_ui_action_tool_messages([ChatMessage.from_tool(tool_result=bulky, origin=origin), plain])

    first = json.loads(slimmed[0].tool_call_result.result)
    assert len(slimmed[0].tool_call_result.result) < 400
    assert first["result"]["ui_action"] == {"dispatched_to_browser": True, "types": ["set_selected_template"]}
    assert first["result"]["status"] == "ui_action_requested"
    assert slimmed[0].tool_call_result.origin.id == "call-1"
    assert slimmed[1] is plain


def test_current_time_block_states_local_date_and_timezone():
    from haystack_pipeline import build_current_time_block

    block = build_current_time_block("Australia/Sydney")
    now = datetime.now(SYDNEY)
    assert "(Australia/Sydney)" in block
    assert f"{now.strftime('%A')} {now.day} {now.strftime('%B %Y')}" in block


def test_web_assistant_prompt_defines_gated_encouraging_voice():
    from personas import PersonaType, persona_manager

    prompt = persona_manager.get_persona(PersonaType.WEB_ASSISTANT).system_prompt
    assert "# YOUR VOICE — IN THE PRACTITIONER'S CORNER" in prompt
    assert "ONE short encouraging line" in prompt
    # Encouragement must be switched off for risk and clinical content.
    assert "When to drop the encouragement completely" in prompt
    assert "client risk, safety, crisis" in prompt
    assert "Invent achievements, breaks, streaks" in prompt
    # The earlier blanket "no sign-off" rule must not contradict the voice.
    assert "no preamble, no sign-off, no" not in prompt.lower()


def test_search_sessions_retries_individual_keywords_before_reporting_no_match(api):
    def respond(method, path, body, params):
        hit = {"id": "transcript-id", "sessionId": "rec", "clientId": CLIENT_ID, "clientName": "Sam Taylor",
               "recordingDate": "2026-11-14T05:57:05.345Z", "duration": 6}
        return {"sessions": [hit] if params.get("keywords") == "investors" else [], "total": 0}

    fake = api({"haystack/search-sessions": respond})

    result = run(tool_manager._search_sessions(client_id=CLIENT_ID, keywords="investor, investors, funding"))

    assert [s["session_id"] for s in result["sessions"]] == ["transcript-id"]
    assert result["search_criteria"]["matched_keywords"] == ["investors"]
    assert len(fake.calls_to("haystack/search-sessions")) == 4


def test_search_sessions_flags_keyword_miss_as_inconclusive(api):
    api({"haystack/search-sessions": {"sessions": [], "total": 0}})
    result = run(tool_manager._search_sessions(client_id=CLIENT_ID, keywords="zzz"))
    assert result["sessions"] == []
    assert "not proof" in result["note"]


def test_navigate_to_page_only_allows_in_app_routes():
    external = run(tool_manager._navigate_to_page(page_url="https://evil.example/x", page_type="other", reason="r"))
    assert external["status"] == "Invalid Request"
    assert "ui_action" not in external

    legacy = run(tool_manager._navigate_to_page(page_url="/live-transcribe", page_type="transcribe_page", reason="r"))
    assert legacy["ui_action"]["payload"]["page_url"] == "/sessions"

    by_type = run(tool_manager._navigate_to_page(page_url="sessions", page_type="transcribe_page", reason="r"))
    assert by_type["ui_action"]["payload"]["page_url"] == "/sessions"


def test_error_classification_reads_status_code_not_stray_digits(api):
    # A validation failure whose body happens to contain "401" in a timestamp
    # must not be reported as an expired login.
    api({"haystack/search-clients": Exception(
        'API request failed: 400 - {"message":["query too long"],"timestamp":"2026-11-15T02:01:14.401Z"}')})
    result = run(tool_manager._search_clients(query="sam"))
    assert result[0]["error_type"] != "Authentication Error"

    api({"haystack/search-clients": Exception(
        'API request failed: 401 - {"message":"Your account is already logged in on another device"}')})
    result = run(tool_manager._search_clients(query="sam"))
    assert result[0]["error_type"] == "Authentication Error"
