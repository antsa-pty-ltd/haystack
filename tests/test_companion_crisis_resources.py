"""
Tests for the B2C ANTSABOT_COMPANION crisis-resource injection
(feature/b2c-pivot code review, finding #1).

The companion has NO practitioner to escalate to, and its crisis protocol
instructs the model to surface country-specific crisis lines. Before the fix,
nothing in this service ever provided those lines and get_system_prompt()
dropped any context for the companion (has_db_access=False) — so the model was
left to hallucinate numbers. These tests pin the receiving end:

  - crisis contacts come from the resolved region's config (regions.REGIONS),
  - an unknown / missing country falls back to the deployment's region
    (COUNTRY_CODE), and to AU only when COUNTRY_CODE is unset,
  - the companion pipeline appends a CRISIS RESOURCES block with concrete
    numbers, keyed off the request's country code.

Region behaviour is proven against the made-up ``zz`` test region (the
``test_region`` fixture in conftest.py), never a real country's entry. AU is
pinned exactly, because AU is live.

No pytest-asyncio dependency — follow the repo's asyncio.run pattern.
"""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from crisis_resources import (  # noqa: E402
    DEFAULT_COUNTRY_CODE,
    build_crisis_continuity_block,
    build_crisis_resources_block,
    get_crisis_resources,
    normalize_country_code,
)
from personas import PersonaType  # noqa: E402

# The AU block exactly as develop rendered it before region config.
DEVELOP_AU_BLOCK = (
    "\n\n# CRISIS RESOURCES (use these exact contacts)\n"
    "These are the crisis lines for the user's region (AU). When the crisis "
    "protocol applies, surface these specific contacts — do NOT invent, guess, "
    "or substitute other numbers. If you are unsure of the user's location, "
    "give the emergency number below and Lifeline/Samaritans/988 as appropriate "
    "and suggest they confirm their local service.\n"
    "- Emergency services: 000 (immediate danger)\n"
    "- Lifeline: 13 11 14 (24/7 crisis support)\n"
    "- Suicide Call Back Service: 1300 659 467 (24/7)\n"
    "- Beyond Blue: 1300 22 4636 (24/7)\n"
    "- 13YARN: 13 92 76 (24/7 support for Aboriginal and Torres Strait Islander people)"
)


# --- crisis_resources module ------------------------------------------------

def test_au_block_matches_develop_except_crisis_line_names():
    """
    AU is live: its block must be the develop text with one deliberate change —
    the "unsure of location" guidance names AU's own crisis line (from config)
    instead of the cross-country "Lifeline/Samaritans/988".
    """
    expected = DEVELOP_AU_BLOCK.replace("Lifeline/Samaritans/988", "Lifeline")
    assert build_crisis_resources_block("au") == expected
    assert build_crisis_resources_block(None) == expected
    assert "Samaritans" not in expected and "988" not in expected


def test_au_block_identical_when_country_code_is_au(monkeypatch):
    unset = build_crisis_resources_block(None)
    monkeypatch.setenv("COUNTRY_CODE", "au")
    assert build_crisis_resources_block(None) == unset
    monkeypatch.setenv("COUNTRY_CODE", " AU ")
    assert build_crisis_resources_block(None) == unset


def test_block_renders_entirely_from_region_config(test_region):
    block = build_crisis_resources_block("zz")
    assert block == (
        "\n\n# CRISIS RESOURCES (use these exact contacts)\n"
        "These are the crisis lines for the user's region (ZZ). When the crisis "
        "protocol applies, surface these specific contacts — do NOT invent, guess, "
        "or substitute other numbers. If you are unsure of the user's location, "
        "give the emergency number below and Testland Helpline/Testland Textline "
        "as appropriate and suggest they confirm their local service.\n"
        "- Testland Emergency: 555 (immediate danger)\n"
        "- Testland Helpline: 0100 200 300 (24/7 crisis support)\n"
        "- Testland Textline: text TEST to 4000 (24/7)\n"
        "- Testland Peer Support: 0100 999 888"
    )
    # Nothing from another region leaks in.
    for foreign in ("13 11 14", "Lifeline", "Samaritans", "988", "911", "Emergency services"):
        assert foreign not in block


def test_missing_or_unknown_country_uses_deployment_region(test_region, monkeypatch):
    monkeypatch.setenv("COUNTRY_CODE", "zz")
    for code in (None, "", "  ", "xx", 42):
        assert normalize_country_code(code) == "zz"
        assert build_crisis_resources_block(code) == build_crisis_resources_block("zz")
    # A supported request code still wins over the deployment region.
    assert normalize_country_code("AU") == "au"
    assert "13 11 14" in build_crisis_resources_block("au")


def test_unset_or_unknown_deployment_falls_back_to_au(test_region, monkeypatch):
    assert DEFAULT_COUNTRY_CODE == "au"
    assert normalize_country_code(None) == "au"
    monkeypatch.setenv("COUNTRY_CODE", "not-a-region")
    assert normalize_country_code(None) == "au"
    assert normalize_country_code(" ZZ ") == "zz"


def test_au_headline_numbers_pinned():
    """The numbers a person in crisis in Australia dials."""
    au = build_crisis_resources_block("au")
    assert "000" in au
    assert "13 11 14" in au


def test_block_instructs_using_exact_contacts():
    block = build_crisis_resources_block("au")
    lower = block.lower()
    assert "crisis resources" in lower
    assert "do not invent" in lower or "do not guess" in lower
    assert "(AU)" in block


def test_block_keeps_crisis_active_across_an_unrelated_follow_up():
    """A topic change must not silently clear an unanswered safety check."""
    block = build_crisis_continuity_block().lower()

    assert "crisis continuity" in block
    assert "remains unresolved" in block
    assert "changes the subject" in block
    assert "explicitly confirms" in block
    assert "i lost my phone" in block
    assert "plain text" in block
    assert "i'm glad" in block


def test_get_crisis_resources_returns_region_contacts(test_region):
    assert get_crisis_resources("zz") == list(test_region.crisis_resources)


# --- pipeline injection -----------------------------------------------------

def _run_companion_prompt(country_code) -> str:
    """
    Drive generate_response_with_chaining far enough to capture the system
    prompt handed to the pipeline, with all I/O (session, redis, OpenAI)
    stubbed. Returns the system prompt string.
    """
    from haystack_pipeline import HaystackPipelineManager

    mgr = HaystackPipelineManager()
    mgr._initialized = True  # skip real pipeline construction

    captured = {}

    def fake_convert(messages, system_prompt):
        captured["system_prompt"] = system_prompt
        # Raise to short-circuit before the (mocked-out) pipeline runs.
        raise _StopForTest()

    fake_session = AsyncMock()
    fake_session.context = {}
    fake_session.profile_id = None
    fake_session.auth_token = None

    context = {}
    if country_code is not None:
        context["country_code"] = country_code

    async def drive():
        with patch("haystack_pipeline.session_manager") as sm, \
             patch.object(mgr, "_convert_to_haystack_messages", side_effect=fake_convert):
            sm.get_session = AsyncMock(return_value=fake_session)
            sm.get_messages = AsyncMock(return_value=[])
            sm.add_message = AsyncMock()
            sm.create_session = AsyncMock()
            try:
                async for _ in mgr.generate_response_with_chaining(
                    session_id="s-test",
                    persona_type=PersonaType.ANTSABOT_COMPANION,
                    user_message="hi",
                    context=context,
                ):
                    pass
            except _StopForTest:
                pass

    asyncio.run(drive())
    return captured["system_prompt"]


class _StopForTest(Exception):
    pass


def test_companion_pipeline_injects_au_lines_when_unconfigured():
    """With no country code anywhere, the companion prompt carries AU lines."""
    prompt = _run_companion_prompt(None)
    assert "CRISIS RESOURCES" in prompt
    assert "CRISIS CONTINUITY" in prompt
    assert "000" in prompt
    assert "13 11 14" in prompt


def test_companion_pipeline_uses_deployment_region_without_request_country(
    test_region, monkeypatch
):
    """A deployment's own region applies when the request names no country."""
    monkeypatch.setenv("COUNTRY_CODE", "zz")
    prompt = _run_companion_prompt(None)
    assert build_crisis_resources_block("zz") in prompt
    assert "13 11 14" not in prompt


def test_companion_pipeline_injects_request_country_lines(test_region):
    """A request country code yields that region's lines, not the default."""
    prompt = _run_companion_prompt("zz")
    assert "Testland Helpline: 0100 200 300" in prompt
    assert "13 11 14" not in prompt


def test_companion_prompt_no_longer_claims_lines_in_context():
    """
    The persona prompt must reference the injected CRISIS RESOURCES block,
    not the old (never-delivered) 'provided to you in this conversation's
    context' channel that the reviewer flagged.
    """
    from personas import persona_manager

    base = persona_manager.get_persona(PersonaType.ANTSABOT_COMPANION).system_prompt
    assert "provided to you in this conversation's context" not in base
    assert "CRISIS RESOURCES" in base or "crisis resources" in base.lower()
