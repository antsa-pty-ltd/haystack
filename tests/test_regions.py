"""
Region configuration (regions.py): resolution order, validation, and that
region-rendered text leaves AU byte-identical to develop.

The AU baseline fixtures in tests/fixtures/au_baseline/ were captured from
origin/develop before region config existed (COUNTRY_CODE unset). Region
behaviour is proven against the made-up ``zz`` region (conftest.py), never a
real country's entry.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from personas import PersonaManager, PersonaType  # noqa: E402
from regions import (  # noqa: E402
    CRISIS_LINE,
    EMERGENCY,
    FALLBACK_COUNTRY_CODE,
    REGIONS,
    CrisisResource,
    Region,
    deployment_country_code,
    get_region,
    render_region_text,
    resolve_country_code,
    validate_region,
)

BASELINE = Path(__file__).parent / "fixtures" / "au_baseline"
EXPORTED = ("web_assistant", "antsabot_therapist", "antsabot_companion")
PROMPTS = EXPORTED + ("transcriber_agent",)


def _baseline(name):
    return json.loads((BASELINE / name).read_text())


# --- resolution -------------------------------------------------------------

def test_fallback_is_au_when_country_code_unset():
    assert FALLBACK_COUNTRY_CODE == "au"
    assert "COUNTRY_CODE" not in os.environ
    assert deployment_country_code() == "au"
    assert get_region().code == "au"


def test_resolution_order(test_region, monkeypatch):
    monkeypatch.setenv("COUNTRY_CODE", "zz")
    assert deployment_country_code() == "zz"
    assert resolve_country_code(None) == "zz"          # deployment region
    assert resolve_country_code("unknown") == "zz"     # unsupported request code
    assert resolve_country_code(" AU ") == "au"        # supported request code wins
    monkeypatch.setenv("COUNTRY_CODE", "unknown")
    assert resolve_country_code(None) == "au"          # fixed fallback


def test_every_configured_region_is_valid():
    for code, region in REGIONS.items():
        assert region.code == code
        validate_region(region)


@pytest.mark.parametrize(
    "resources",
    [
        (CrisisResource("Line", "1", kind=CRISIS_LINE),),  # no emergency
        (CrisisResource("E", "1", kind=EMERGENCY),),       # no crisis line
        (
            CrisisResource("E", "1", kind=EMERGENCY),
            CrisisResource("E2", "2", kind=EMERGENCY),
            CrisisResource("Line", "3", kind=CRISIS_LINE),
        ),
        (
            CrisisResource("E", "1", kind=EMERGENCY),
            CrisisResource("Line", " ", kind=CRISIS_LINE),
        ),
    ],
)
def test_unsafe_region_is_rejected(resources):
    with pytest.raises(ValueError):
        validate_region(Region("qq", "Q English", "UTC", resources))


# --- text rendering ---------------------------------------------------------

def test_render_fills_placeholders_and_leaves_bare_dollars(test_region):
    text = "Write in ${language_variety}. A $50 fee; $HOME stays."
    assert render_region_text(text, test_region) == (
        "Write in Testland English. A $50 fee; $HOME stays."
    )


def test_render_rejects_unknown_placeholder(test_region):
    with pytest.raises(KeyError):
        render_region_text("${not_a_region_value}", test_region)


# --- personas: AU unchanged -------------------------------------------------

@pytest.mark.parametrize("country_code", [None, "au", "AU"])
def test_au_persona_prompts_identical_to_develop(monkeypatch, country_code):
    if country_code:
        monkeypatch.setenv("COUNTRY_CODE", country_code)
    manager = PersonaManager()
    baseline = _baseline("persona_system_prompts.json")
    for name in PROMPTS:
        assert manager.personas[PersonaType(name)].system_prompt == baseline[name], name


@pytest.mark.parametrize("country_code", [None, "au"])
def test_au_persona_defaults_export_identical_to_develop(monkeypatch, country_code):
    """What /internal/persona-defaults serves an AU deployment is unchanged."""
    if country_code:
        monkeypatch.setenv("COUNTRY_CODE", country_code)
    manager = PersonaManager()
    baseline = _baseline("persona_defaults_export.json")
    for name in EXPORTED:
        assert manager.export_default(PersonaType(name)) == baseline[name], name


def test_no_placeholder_survives_rendering():
    manager = PersonaManager()
    for name in PROMPTS:
        assert "${" not in manager.personas[PersonaType(name)].system_prompt


# --- personas: other regions ------------------------------------------------

def test_persona_defaults_follow_deployment_region(test_region, monkeypatch):
    """A new region imports version 1 in its own language variety."""
    au = _baseline("persona_defaults_export.json")
    monkeypatch.setenv("COUNTRY_CODE", "zz")
    from personas import persona_manager  # built at import for the AU fallback

    for name in EXPORTED:
        exported = persona_manager.export_default(PersonaType(name))
        assert "Australian" not in exported["systemPrompt"], name
        # Only the language variety differs from AU.
        assert exported["systemPrompt"] == au[name]["systemPrompt"].replace(
            "Australian English", "Testland English"
        ), name
        assert {k: v for k, v in exported.items() if k != "systemPrompt"} == {
            k: v for k, v in au[name].items() if k != "systemPrompt"
        }
    assert "Testland English" in persona_manager.export_default(
        PersonaType.WEB_ASSISTANT
    )["systemPrompt"]


def test_persona_manager_renders_for_its_region(test_region):
    manager = PersonaManager(country_code="zz")
    for name in PROMPTS:
        prompt = manager.personas[PersonaType(name)].system_prompt
        assert "Australian English" not in prompt, name
    assert "(Testland English)" in manager.personas[PersonaType.TRANSCRIBER_AGENT].system_prompt
    # The legacy alias still shares the therapist config.
    assert (
        manager.personas[PersonaType.JAIMEE_THERAPIST]
        is manager.personas[PersonaType.ANTSABOT_THERAPIST]
    )


# --- document generation ----------------------------------------------------

def test_au_document_language_instructions_identical_to_develop(monkeypatch):
    from document_generation.language import output_language_rules

    baseline = (BASELINE / "document_language_instructions.txt").read_text()
    assert output_language_rules() == baseline
    monkeypatch.setenv("COUNTRY_CODE", "au")
    assert output_language_rules() == baseline


def test_document_language_follows_deployment_region(test_region, monkeypatch):
    from document_generation.language import output_language_rules

    baseline = (BASELINE / "document_language_instructions.txt").read_text()
    monkeypatch.setenv("COUNTRY_CODE", "zz")
    assert output_language_rules() == baseline.replace("Australian English", "Testland English")


# --- timezone ---------------------------------------------------------------

def test_timezone_default_follows_deployment_region(test_region, monkeypatch):
    from tools import ToolManager

    manager = ToolManager()
    manager.current_page_context = {}
    for var in ("TZ", "TIMEZONE"):
        monkeypatch.delenv(var, raising=False)

    # Unset COUNTRY_CODE keeps develop's behaviour: UTC, not a guessed region.
    assert manager._resolve_timezone()[1] == "UTC"
    monkeypatch.setenv("COUNTRY_CODE", "au")
    assert manager._resolve_timezone()[1] == "Australia/Sydney"
    monkeypatch.setenv("COUNTRY_CODE", "zz")
    assert manager._resolve_timezone()[1] == "Pacific/Chatham"
    # Browser timezone still wins.
    manager.current_page_context = {"timezone": "Australia/Perth"}
    assert manager._resolve_timezone()[1] == "Australia/Perth"
