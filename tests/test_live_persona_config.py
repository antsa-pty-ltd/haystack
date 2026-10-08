from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = "sk-test-dummy-key"

from haystack_pipeline import HaystackPipelineManager  # noqa: E402
from persona_config_provider import PersonaConfigProvider, PublishedPersonaConfig  # noqa: E402
from personas import PersonaType, persona_manager  # noqa: E402
from llm_routing import (  # noqa: E402
    LlmWorkloadRouter,
    THERAPIST_FOUNDRY_ALIAS_ENV,
    THERAPIST_OPENAI_ALIAS_ENV,
    THERAPIST_ROUTE_ENV,
    THERAPIST_WORKLOAD,
    router_registry,
)


def _published(**overrides) -> PublishedPersonaConfig:
    values = {
        "version": 7,
        "name": "Live client persona",
        "description": "Configuration published by an administrator",
        "systemPrompt": "You are the live client persona. Follow the published safety contract.",
        "model": "gpt-5.2",
        "temperature": 0.35,
        "maxCompletionTokens": 777,
        "hasDbAccess": False,
        "toolNames": ["breathing_exercise"],
    }
    values.update(overrides)
    return PublishedPersonaConfig.model_validate(values)


def test_deployed_defaults_export_every_runtime_setting_and_safe_tool_name():
    default = persona_manager.export_default(PersonaType.ANTSABOT_THERAPIST)

    assert default["persona"] == "antsabot_therapist"
    assert default["systemPrompt"].startswith("You are ANTSAbot")
    assert default["model"] == "gpt-5.2"
    assert default["temperature"] == 0.8
    assert default["maxCompletionTokens"] == 1024
    assert default["hasDbAccess"] is False
    assert "breathing_exercise" in default["toolNames"]


def test_published_config_controls_generator_and_tool_set_without_restart():
    provider = PersonaConfigProvider()
    config = provider._build_config(PersonaType.ANTSABOT_THERAPIST, _published())
    manager = HaystackPipelineManager()

    manager._create_antsabot_therapist_pipeline(config)
    pipeline = manager.pipelines[PersonaType.ANTSABOT_THERAPIST]
    generator = pipeline.get_component("generator")
    tool_invoker = pipeline.get_component("tool_invoker")

    assert config.version == 7
    assert config.system_prompt.startswith("You are the live client persona")
    assert generator.model == "gpt-5.2"
    assert generator.generation_kwargs == {
        "temperature": 0.35,
        "max_completion_tokens": 777,
    }
    assert [tool.name for tool in tool_invoker.tools] == ["breathing_exercise"]
    assert manager._pipeline_signatures[PersonaType.ANTSABOT_THERAPIST][0] == 7


def test_published_config_cannot_expand_a_client_persona_tool_scope():
    provider = PersonaConfigProvider()

    with pytest.raises(ValueError, match="unavailable tools: search_clients"):
        provider._build_config(
            PersonaType.ANTSABOT_THERAPIST,
            _published(toolNames=["search_clients"]),
        )


def test_routed_persona_hot_reload_keeps_server_alias_and_updates_other_settings():
    alias = "antsa-haystack-therapist-openai"
    router_registry.register(
        LlmWorkloadRouter(
            workload=THERAPIST_WORKLOAD,
            route_env=THERAPIST_ROUTE_ENV,
            openai_alias_env=THERAPIST_OPENAI_ALIAS_ENV,
            foundry_alias_env=THERAPIST_FOUNDRY_ALIAS_ENV,
            environ={
                THERAPIST_ROUTE_ENV: "litellm_openai",
                THERAPIST_OPENAI_ALIAS_ENV: alias,
                "LLM_GATEWAY_BASE_URL": "https://gateway.example/v1",
                "HAYSTACK_LLM_GATEWAY_API_KEY": "scoped-test-key",
            },
        )
    )
    provider = PersonaConfigProvider()
    manager = HaystackPipelineManager()
    first = provider._build_config(
        PersonaType.ANTSABOT_THERAPIST,
        _published(model="gpt-5.2", temperature=0.2, maxCompletionTokens=500),
    )
    changed = provider._build_config(
        PersonaType.ANTSABOT_THERAPIST,
        _published(
            version=8,
            model="gpt-5.4-mini",
            temperature=0.6,
            maxCompletionTokens=900,
        ),
    )

    manager._create_antsabot_therapist_pipeline(first)
    first_generator = manager.pipelines[PersonaType.ANTSABOT_THERAPIST].get_component("generator")
    manager._create_antsabot_therapist_pipeline(changed)
    changed_generator = manager.pipelines[PersonaType.ANTSABOT_THERAPIST].get_component("generator")

    assert first_generator.model == alias
    assert changed_generator.model == alias
    assert changed_generator.generation_kwargs == {
        "temperature": 0.6,
        "max_completion_tokens": 900,
    }
