"""
Tests for the B2C ANTSABOT_COMPANION crisis-resource injection
(feature/b2c-pivot code review, finding #1).

The companion has NO practitioner to escalate to, and its crisis protocol
instructs the model to surface country-specific crisis lines. Before the fix,
nothing in this service ever provided those lines and get_system_prompt()
dropped any context for the companion (has_db_access=False) — so the model was
left to hallucinate numbers. These tests pin the receiving end:

  - crisis_resources owns concrete contacts per supported country (AU/US/UK),
  - an unknown / missing country falls back to the platform default (au),
  - the companion pipeline appends a CRISIS RESOURCES block with concrete
    numbers, keyed off the request's country code.

No pytest-asyncio dependency — follow the repo's asyncio.run pattern.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import List
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from crisis_resources import (  # noqa: E402
    DEFAULT_COUNTRY_CODE,
    CRISIS_RESOURCES,
    build_crisis_resources_block,
    get_crisis_resources,
    normalize_country_code,
)
from personas import PersonaType  # noqa: E402


# --- crisis_resources module ------------------------------------------------

def test_supported_countries_have_concrete_contacts():
    """AU/US/UK each expose at least an emergency number + a crisis line."""
    for code in ("au", "us", "uk"):
        resources = CRISIS_RESOURCES[code]
        assert len(resources) >= 2
        rendered = "\n".join(r.render() for r in resources).lower()
        assert "emergency" in rendered  # an emergency-services contact exists
        # Every contact renders a non-empty number/instruction.
        for r in resources:
            assert r.contact.strip()


def test_concrete_known_numbers_present():
    """
    Pin the well-known headline numbers so a careless edit that blanks or
    mangles them fails loudly (these are the numbers a person in crisis dials).
    """
    au = build_crisis_resources_block("au")
    assert "000" in au          # AU emergency
    assert "13 11 14" in au     # Lifeline

    us = build_crisis_resources_block("us")
    assert "911" in us          # US emergency
    assert "988" in us          # 988 Lifeline

    uk = build_crisis_resources_block("uk")
    assert "999" in uk          # UK emergency
    assert "116 123" in uk      # Samaritans


def test_normalize_country_code_fuzzy_and_fallback():
    assert normalize_country_code("AU") == "au"
    assert normalize_country_code("  Us ") == "us"
    assert normalize_country_code("uk") == "uk"
    # Unknown / missing fall back to the platform default.
    assert normalize_country_code("nz") == DEFAULT_COUNTRY_CODE
    assert normalize_country_code(None) == DEFAULT_COUNTRY_CODE
    assert normalize_country_code("") == DEFAULT_COUNTRY_CODE
    assert DEFAULT_COUNTRY_CODE == "au"


def test_unknown_country_block_falls_back_to_default():
    """An unknown country still yields concrete (default-country) numbers."""
    block = build_crisis_resources_block("zz")
    default_block = build_crisis_resources_block(DEFAULT_COUNTRY_CODE)
    assert block == default_block
    assert "000" in block  # never empty / never a placeholder


def test_block_instructs_using_exact_contacts():
    block = build_crisis_resources_block("au")
    lower = block.lower()
    assert "crisis resources" in lower
    assert "do not invent" in lower or "do not guess" in lower
    # Names the resolved region.
    assert "(AU)" in block


def test_get_crisis_resources_returns_resource_objects():
    resources: List = get_crisis_resources("us")
    assert resources is CRISIS_RESOURCES["us"]


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


def test_companion_pipeline_injects_default_crisis_lines():
    """With no country code, the companion prompt carries AU (default) lines."""
    prompt = _run_companion_prompt(None)
    assert "CRISIS RESOURCES" in prompt
    assert "000" in prompt          # AU emergency (default)
    assert "13 11 14" in prompt     # Lifeline


def test_companion_pipeline_injects_country_specific_lines():
    """A US country code yields US crisis lines, not the default AU ones."""
    prompt = _run_companion_prompt("us")
    assert "988" in prompt
    assert "911" in prompt
    # The default AU emergency number must NOT be what we surface for a US user.
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
