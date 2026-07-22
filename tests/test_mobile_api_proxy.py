"""Regression tests for the API-owned mobile ANTSAbot bridge."""

from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = "sk-test-dummy-key"

import haystack_pipeline as pipeline_module  # noqa: E402
from haystack_pipeline import HaystackPipelineManager  # noqa: E402
from personas import PersonaType  # noqa: E402
from service_auth import is_valid_service_secret  # noqa: E402


def test_service_secret_fails_closed_and_uses_exact_match(monkeypatch):
    monkeypatch.delenv("HAYSTACK_WEBHOOK_SECRET", raising=False)
    assert is_valid_service_secret(None) is False
    assert is_valid_service_secret("anything") is False

    monkeypatch.setenv("HAYSTACK_WEBHOOK_SECRET", "correct-secret")
    assert is_valid_service_secret(None) is False
    assert is_valid_service_secret("wrong-secret") is False
    assert is_valid_service_secret("correct-secret") is True


def test_tool_credentials_are_isolated_between_concurrent_client_tasks():
    async def worker(token, profile_id, delay):
        pipeline_module.tool_manager.set_auth_token(token, profile_id)
        pipeline_module.tool_manager.set_page_context({"client_id": profile_id})
        await asyncio.sleep(delay)
        return (
            pipeline_module.tool_manager.auth_token,
            pipeline_module.tool_manager.profile_id,
            pipeline_module.tool_manager.current_page_context,
        )

    async def run_workers():
        return await asyncio.gather(
            worker("jwt-client-a", "client-a", 0.01),
            worker("jwt-client-b", "client-b", 0),
        )

    first, second = asyncio.run(run_workers())
    assert first == ("jwt-client-a", "client-a", {"client_id": "client-a"})
    assert second == ("jwt-client-b", "client-b", {"client_id": "client-b"})


class _FakeGenerator:
    def __init__(self, error: Exception | None = None):
        self.messages = None
        self.error = error

    def run(self, messages):
        self.messages = messages
        if self.error:
            raise self.error
        return {"replies": [SimpleNamespace(content="A safe response", tool_calls=[])]}


class _FakeRouter:
    def run(self, replies):
        return {"no_tool_calls": replies}


class _FakePipeline:
    def __init__(self, generator):
        self.generator = generator
        self.graph = SimpleNamespace(
            nodes={"message_collector", "generator", "router", "tool_invoker"}
        )

    def get_component(self, name):
        if name == "generator":
            return self.generator
        if name == "router":
            return _FakeRouter()
        return SimpleNamespace()


def _install_session_doubles(monkeypatch):
    messages = []
    requested_limits = []

    async def get_session(_session_id):
        return SimpleNamespace(context={}, profile_id="client-123", auth_token=None)

    async def get_messages(_session_id, limit=None):
        requested_limits.append(limit)
        return messages[-limit:] if limit else list(messages)

    async def add_message(_session_id, role, content):
        messages.append(SimpleNamespace(role=role, content=content))

    async def get_state(_session_id):
        return {}

    monkeypatch.setattr(pipeline_module.session_manager, "get_session", get_session)
    monkeypatch.setattr(pipeline_module.session_manager, "get_messages", get_messages)
    monkeypatch.setattr(pipeline_module.session_manager, "add_message", add_message)

    import ui_state_manager

    monkeypatch.setattr(ui_state_manager.ui_state_manager, "get_state", get_state)
    return messages, requested_limits


def test_trusted_mobile_prompt_override_and_legacy_history_limit_are_used(monkeypatch):
    _messages, requested_limits = _install_session_doubles(monkeypatch)
    generator = _FakeGenerator()
    manager = HaystackPipelineManager()
    manager._initialized = True
    manager.pipelines[PersonaType.ANTSABOT_COMPANION] = _FakePipeline(generator)

    # The trusted API prompt already contains client-specific crisis and
    # practitioner context. The generic companion block must not be appended.
    monkeypatch.setattr(
        pipeline_module,
        "build_crisis_resources_block",
        lambda _country: (_ for _ in ()).throw(
            AssertionError("generic crisis block should not be duplicated")
        ),
    )

    async def collect():
        return [
            chunk
            async for chunk in manager.generate_response_with_chaining(
                session_id="mobile-session",
                persona_type=PersonaType.ANTSABOT_COMPANION,
                user_message="I need help",
                context={
                    "_trusted_api_proxy": True,
                    "system_prompt_override": (
                        "Trusted prompt for [CLIENT_NAME], whose practitioner is "
                        "[PRACTITIONER_FIRST_NAME], with existing safety guardrails."
                    ),
                    "history_limit": 201,
                },
            )
        ]

    assert "".join(asyncio.run(collect())) == "A safe response"
    assert requested_limits[-1] == 201
    assert generator.messages[0].text.startswith("Trusted prompt for [CLIENT_NAME]")


def test_api_proxy_generation_errors_propagate_instead_of_becoming_fake_success(monkeypatch):
    _install_session_doubles(monkeypatch)
    manager = HaystackPipelineManager()
    manager._initialized = True
    manager.pipelines[PersonaType.ANTSABOT_THERAPIST] = _FakePipeline(
        _FakeGenerator(RuntimeError("generator failed"))
    )

    async def collect():
        return [
            chunk
            async for chunk in manager.generate_response_with_chaining(
                session_id="mobile-session",
                persona_type=PersonaType.ANTSABOT_THERAPIST,
                user_message="Hello",
                context={"_trusted_api_proxy": True, "_propagate_errors": True},
            )
        ]

    with pytest.raises(RuntimeError, match="generator failed"):
        asyncio.run(collect())
