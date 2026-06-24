"""
Tests for practitioner-context injection into ANTSAbot personas.

The companion and therapist personas previously gave generic "speak to a
professional" advice. Now the system prompt is augmented with a PRACTITIONER
CONTEXT block that names the client's practitioner (if any), so the model can
give contextually appropriate recommendations.

Three scenarios:
  A) B2B practitioner-assigned chat — name the practitioner
  B) B2C client who connected with a practitioner — name the practitioner
  C) Pure B2C / no practitioner — suggest in-app "Connect with a practitioner"

No pytest-asyncio dependency — follow the repo's asyncio.run pattern.
"""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from practitioner_context import (  # noqa: E402
    build_practitioner_context_block,
    fetch_practitioner_context,
)
from personas import PersonaType, persona_manager  # noqa: E402


# --- build_practitioner_context_block unit tests ----------------------------


def test_scenario_a_b2b_practitioner():
    """Scenario A: B2B client has a named practitioner."""
    block = build_practitioner_context_block({
        "hasPractitioner": True,
        "firstName": "Sally",
        "practitionerType": "Psychologist",
        "isB2c": False,
    })
    assert "PRACTITIONER CONTEXT" in block
    assert "Sally" in block
    assert "Psychologist" in block
    # Should NOT suggest "Connect with a practitioner"
    assert "Connect with a practitioner" not in block
    # Should mention crisis resources as primary in crisis
    assert "crisis" in block.lower()


def test_scenario_b_b2c_with_practitioner():
    """Scenario B: B2C client who has connected with a practitioner."""
    block = build_practitioner_context_block({
        "hasPractitioner": True,
        "firstName": "James",
        "practitionerType": "Counsellor",
        "isB2c": True,
    })
    assert "PRACTITIONER CONTEXT" in block
    assert "James" in block
    assert "Counsellor" in block
    assert "ANTSA" in block
    assert "crisis" in block.lower()


def test_scenario_c_no_practitioner():
    """Scenario C: no practitioner — suggest in-app connection."""
    block = build_practitioner_context_block({
        "hasPractitioner": False,
    })
    assert "PRACTITIONER CONTEXT" in block
    assert "Connect with a practitioner" in block
    assert "Do NOT claim" in block
    assert "crisis" in block.lower()


def test_none_input_treated_as_no_practitioner():
    """None input (fetch failed) falls back to no-practitioner scenario."""
    block = build_practitioner_context_block(None)
    assert "Connect with a practitioner" in block
    assert "Do NOT claim" in block


def test_missing_practitioner_type_uses_fallback():
    """If practitionerType is missing/null, fall back to 'practitioner'."""
    block = build_practitioner_context_block({
        "hasPractitioner": True,
        "firstName": "Alex",
        "practitionerType": None,
        "isB2c": False,
    })
    assert "Alex" in block
    assert "practitioner" in block.lower()


# --- persona prompt tests ---------------------------------------------------


def test_companion_prompt_references_practitioner_context_section():
    """The companion persona prompt tells the model to look for PRACTITIONER CONTEXT."""
    base = persona_manager.get_persona(PersonaType.ANTSABOT_COMPANION).system_prompt
    assert "PRACTITIONER CONTEXT" in base
    # The old hardcoded "NO practitioner" claim must be gone.
    assert "there is NO practitioner" not in base


def test_therapist_prompt_references_practitioner_context_section():
    """The therapist persona prompt tells the model to look for PRACTITIONER CONTEXT."""
    base = persona_manager.get_persona(PersonaType.ANTSABOT_THERAPIST).system_prompt
    assert "PRACTITIONER CONTEXT" in base


# --- pipeline injection tests -----------------------------------------------


class _StopForTest(Exception):
    pass


def _run_persona_prompt(persona_type, auth_token="fake-jwt", pract_response=None) -> str:
    """
    Drive generate_response_with_chaining far enough to capture the system
    prompt handed to the pipeline, with all I/O stubbed. Returns the system
    prompt string.
    """
    from haystack_pipeline import HaystackPipelineManager

    mgr = HaystackPipelineManager()
    mgr._initialized = True

    captured = {}

    def fake_convert(messages, system_prompt):
        captured["system_prompt"] = system_prompt
        raise _StopForTest()

    fake_session = AsyncMock()
    fake_session.context = {}
    fake_session.profile_id = None
    fake_session.auth_token = auth_token

    async def mock_fetch(token, api_base_url=None):
        return pract_response

    async def drive():
        with patch("haystack_pipeline.session_manager") as sm, \
             patch.object(mgr, "_convert_to_haystack_messages", side_effect=fake_convert), \
             patch("haystack_pipeline.fetch_practitioner_context", side_effect=mock_fetch):
            sm.get_session = AsyncMock(return_value=fake_session)
            sm.get_messages = AsyncMock(return_value=[])
            sm.add_message = AsyncMock()
            sm.create_session = AsyncMock()
            try:
                async for _ in mgr.generate_response_with_chaining(
                    session_id="s-test",
                    persona_type=persona_type,
                    user_message="I feel really low",
                    context={},
                ):
                    pass
            except _StopForTest:
                pass

    asyncio.run(drive())
    return captured.get("system_prompt", "")


def test_companion_pipeline_injects_practitioner_with_name():
    """Companion pipeline injects a named practitioner when one exists."""
    prompt = _run_persona_prompt(
        PersonaType.ANTSABOT_COMPANION,
        pract_response={
            "hasPractitioner": True,
            "firstName": "Sally",
            "practitionerType": "Psychologist",
            "isB2c": False,
        },
    )
    assert "PRACTITIONER CONTEXT" in prompt
    assert "Sally" in prompt
    assert "Psychologist" in prompt


def test_companion_pipeline_injects_no_practitioner_fallback():
    """Companion pipeline injects no-practitioner guidance when none exists."""
    prompt = _run_persona_prompt(
        PersonaType.ANTSABOT_COMPANION,
        pract_response={"hasPractitioner": False},
    )
    assert "PRACTITIONER CONTEXT" in prompt
    assert "Connect with a practitioner" in prompt


def test_therapist_pipeline_injects_practitioner_context():
    """Therapist pipeline also gets practitioner context."""
    prompt = _run_persona_prompt(
        PersonaType.ANTSABOT_THERAPIST,
        pract_response={
            "hasPractitioner": True,
            "firstName": "James",
            "practitionerType": "Counsellor",
            "isB2c": False,
        },
    )
    assert "PRACTITIONER CONTEXT" in prompt
    assert "James" in prompt


def test_web_assistant_not_affected():
    """WEB_ASSISTANT persona should NOT get practitioner context injection."""
    prompt = _run_persona_prompt(
        PersonaType.WEB_ASSISTANT,
        pract_response={
            "hasPractitioner": True,
            "firstName": "Sally",
            "practitionerType": "Psychologist",
            "isB2c": False,
        },
    )
    # WEB_ASSISTANT should not have PRACTITIONER CONTEXT injected
    # (the injection only runs for COMPANION and THERAPIST)
    assert "Sally" not in prompt
