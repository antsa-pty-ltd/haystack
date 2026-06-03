"""
Tests for the B2C ANTSABOT_COMPANION persona (feature/b2c-pivot).

The companion is a wellbeing companion for self-signup (B2C) users who have no
practitioner behind them. It is derived from ANTSABOT_THERAPIST but with:
  - explicit "I'm not a therapist / this isn't therapy" framing (no diagnosis,
    no treatment claims — SaMD/AHPRA posture),
  - a hardened crisis protocol that NEVER assumes a practitioner exists to
    escalate to (country crisis lines are injected upstream by the API),
  - gentle care-steering toward a professional + the in-app
    "Connect with your practitioner" option,
  - the SAME model/temperature/token settings and EXACTLY the same client-scoped
    tool set as the therapist persona.

These tests pin the contract and guard the therapist persona against drift.
No pytest-asyncio dependency — follow the repo's asyncio.run pattern.
"""

from __future__ import annotations

import os
import sys

# Make repo importable when run from anywhere.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from personas import PersonaType, persona_manager  # noqa: E402


def _tool_names(config) -> list:
    return sorted(t["function"]["name"] for t in config.tools)


def test_companion_enum_value():
    """The enum member exists and serialises to the spec string."""
    assert PersonaType.ANTSABOT_COMPANION.value == "antsabot_companion"


def test_companion_registered_in_manager():
    """The companion persona is registered with a resolvable config."""
    config = persona_manager.get_persona(PersonaType.ANTSABOT_COMPANION)
    assert config is not None
    assert config.name == "ANTSAbot"


def test_companion_resolvable_by_string_name():
    """
    Inbound requests carry a raw persona string; PersonaType(string) is how
    main.py resolves it. The companion must round-trip from its string name.
    """
    resolved = PersonaType("antsabot_companion")
    assert resolved is PersonaType.ANTSABOT_COMPANION

    config = persona_manager.get_persona(resolved)
    assert config is not None
    # get_system_prompt must not raise for the resolved persona.
    prompt = persona_manager.get_system_prompt(resolved)
    assert isinstance(prompt, str) and len(prompt) > 0


def test_companion_tool_list_exactly_matches_therapist():
    """
    Same client-scoped tool set as the therapist — no more, no fewer, no new
    tools. The spec is explicit: mood_check_in, coping_strategies,
    breathing_exercise, get_client_mood_profile, get_user_profile.
    """
    companion = persona_manager.get_persona(PersonaType.ANTSABOT_COMPANION)
    therapist = persona_manager.get_persona(PersonaType.ANTSABOT_THERAPIST)

    expected = sorted([
        "mood_check_in",
        "coping_strategies",
        "breathing_exercise",
        "get_client_mood_profile",
        "get_user_profile",
    ])

    assert _tool_names(companion) == expected
    assert _tool_names(companion) == _tool_names(therapist)


def test_companion_shares_model_temperature_token_settings_with_therapist():
    """Same mini-class model/temperature/token settings; has_db_access False."""
    companion = persona_manager.get_persona(PersonaType.ANTSABOT_COMPANION)
    therapist = persona_manager.get_persona(PersonaType.ANTSABOT_THERAPIST)

    assert companion.model == therapist.model
    assert companion.temperature == therapist.temperature
    assert companion.max_completion_tokens == therapist.max_completion_tokens
    assert companion.has_db_access is False


def test_companion_prompt_has_not_a_therapist_framing():
    """Explicit not-a-therapist / not-therapy framing must be present."""
    prompt = persona_manager.get_persona(PersonaType.ANTSABOT_COMPANION).system_prompt
    lower = prompt.lower()

    assert "wellbeing companion" in lower
    assert "not a therapist" in lower
    assert "not therapy" in lower
    # No-diagnosis / no-treatment-claim posture.
    assert "never diagnose" in lower
    assert "treatment claims" in lower


def test_companion_prompt_has_hardened_crisis_protocol():
    """
    Crisis protocol must instruct using injected crisis lines + direct emergency
    contact, and must NOT assume a practitioner/human will escalate.
    """
    prompt = persona_manager.get_persona(PersonaType.ANTSABOT_COMPANION).system_prompt
    lower = prompt.lower()

    assert "crisis" in lower
    # Uses upstream-injected country crisis lines.
    assert "crisis lines" in lower
    # Directs to emergency services directly.
    assert "emergency services" in lower
    # Self-harm / suicide handling is named.
    assert "self-harm" in lower or "suicide" in lower
    # Never claims a human is monitoring / will be alerted.
    assert "no practitioner" in lower or "no practitioner or care team" in lower


def test_companion_prompt_has_care_steering():
    """Gentle steering toward a professional + the in-app connect option."""
    prompt = persona_manager.get_persona(PersonaType.ANTSABOT_COMPANION).system_prompt

    assert "Connect with your practitioner" in prompt
    lower = prompt.lower()
    assert "mental health professional" in lower or "professional" in lower
    # Steering must be framed as gentle / non-pushy.
    assert "gentle" in lower or "non-pushy" in lower


# --- Therapist persona unchanged (snapshot-style guards) ---------------------

# Captured from ANTSABOT_THERAPIST at the time the companion was added. If the
# therapist persona is modified, these break — proving the change wasn't
# isolated to the companion.
_THERAPIST_PROMPT_OPENING = (
    "You are ANTSAbot, a warm, empathetic therapist providing mental health support."
)
_THERAPIST_PROMPT_CLOSING = "Respect cultural and individual differences"


def test_therapist_persona_config_unchanged():
    """The therapist persona's settings must be untouched by this change."""
    therapist = persona_manager.get_persona(PersonaType.ANTSABOT_THERAPIST)

    assert therapist.name == "ANTSAbot"
    assert therapist.model == "gpt-5.2"
    assert therapist.temperature == 0.8
    assert therapist.max_completion_tokens == 1024
    assert therapist.has_db_access is False
    assert _tool_names(therapist) == sorted([
        "mood_check_in",
        "coping_strategies",
        "breathing_exercise",
        "get_client_mood_profile",
        "get_user_profile",
    ])


def test_therapist_prompt_unchanged_snapshot():
    """
    Snapshot-style assertion on the therapist prompt boundaries and the fact
    that it describes itself as a therapist (the companion does NOT). This is
    the guard that the companion was added without editing the therapist.
    """
    therapist = persona_manager.get_persona(PersonaType.ANTSABOT_THERAPIST)
    prompt = therapist.system_prompt

    assert prompt.strip().startswith(_THERAPIST_PROMPT_OPENING)
    assert prompt.strip().endswith(_THERAPIST_PROMPT_CLOSING)
    # Therapist self-describes as a therapist; companion must not.
    assert "empathetic therapist" in prompt
    # The companion-only framing must NOT have leaked into the therapist prompt.
    assert "wellbeing companion" not in prompt.lower()
    assert "not a therapist" not in prompt.lower()
    assert "Connect with your practitioner" not in prompt


def test_jaimee_legacy_alias_still_points_at_therapist():
    """
    Backward-compat: the deprecated jaimee_therapist persona still resolves to
    the therapist config (companion did not disturb the legacy mapping).
    """
    jaimee = persona_manager.get_persona(PersonaType.JAIMEE_THERAPIST)
    therapist = persona_manager.get_persona(PersonaType.ANTSABOT_THERAPIST)
    assert jaimee is therapist
