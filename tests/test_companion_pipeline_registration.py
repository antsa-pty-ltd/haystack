"""
Tests that the B2C ANTSABOT_COMPANION pipeline is actually registered and
selectable (feature/b2c-pivot code review, finding #2).

Runtime dispatch in haystack_pipeline.py does
`pipeline = self.pipelines.get(persona_type)` and raises
"Pipeline not available for {persona_type}" when missing. The companion needs
BOTH the persona entry (personas.py) AND _create_antsabot_companion_pipeline()
registering self.pipelines[PersonaType.ANTSABOT_COMPANION]. The persona-only
tests can't catch a dropped/renamed pipeline registration — a future edit that
removes the _create call (or its invocation in initialize()) would pass every
persona test but 500 every companion chat at runtime.

These tests initialise a real HaystackPipelineManager and assert the companion
pipeline is present and shaped like the therapist's (same components, no UI
collector).

No pytest-asyncio dependency — follow the repo's asyncio.run pattern.
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# OpenAIChatGenerator construction needs a non-empty key (no network call is
# made at construction time). CI exports OPENAI_API_KEY as an empty string, so
# setdefault() is not enough — force a dummy whenever it's missing OR blank.
if not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = "sk-test-dummy-key"

from personas import PersonaType  # noqa: E402
from haystack_pipeline import HaystackPipelineManager  # noqa: E402


def _initialized_manager() -> HaystackPipelineManager:
    mgr = HaystackPipelineManager()
    asyncio.run(mgr.initialize())
    return mgr


def _component_names(pipeline) -> set:
    return set(pipeline.graph.nodes)


def test_companion_pipeline_registered_and_selectable():
    """initialize() must register a pipeline under ANTSABOT_COMPANION."""
    mgr = _initialized_manager()
    assert PersonaType.ANTSABOT_COMPANION in mgr.pipelines
    pipeline = mgr.pipelines.get(PersonaType.ANTSABOT_COMPANION)
    assert pipeline is not None


def test_companion_pipeline_shaped_like_therapist():
    """
    Same components as the therapist pipeline (message_collector, generator,
    router, tool_invoker) and — like the therapist — NO ui_collector.
    """
    mgr = _initialized_manager()
    companion = mgr.pipelines[PersonaType.ANTSABOT_COMPANION]
    therapist = mgr.pipelines[PersonaType.ANTSABOT_THERAPIST]

    expected = {"message_collector", "generator", "router", "tool_invoker"}
    assert _component_names(companion) == expected
    assert _component_names(companion) == _component_names(therapist)
    # The companion (like the therapist) has no UI action collector.
    assert "ui_collector" not in _component_names(companion)


def test_web_assistant_pipeline_has_ui_collector_companion_does_not():
    """Guard against the companion accidentally adopting the web_assistant shape."""
    mgr = _initialized_manager()
    web = mgr.pipelines[PersonaType.WEB_ASSISTANT]
    companion = mgr.pipelines[PersonaType.ANTSABOT_COMPANION]
    assert "ui_collector" in _component_names(web)
    assert "ui_collector" not in _component_names(companion)


def test_dispatch_would_not_raise_pipeline_not_available():
    """
    Mirror the runtime guard: get(persona_type) must be truthy so dispatch
    never reaches `raise Exception("Pipeline not available ...")`.
    """
    mgr = _initialized_manager()
    assert mgr.pipelines.get(PersonaType.ANTSABOT_COMPANION) is not None
