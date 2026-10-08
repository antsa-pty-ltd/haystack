from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.utils import Secret
from fastapi import HTTPException

from agents.document_agent import DocumentExplorationAgent
from haystack_pipeline import HaystackPipelineManager
from llm_routing import ALL_LLM_WORKLOADS, LlmRoute, LlmRouterRegistry, LlmWorkloadRouter
from personas import PersonaType, persona_manager
from release_identity import release_sha
from routed_generator import RoutedOpenAIChatGenerator


WORKLOADS = (
    "chat",
    "companion",
    "conversation_summary",
    "document_agent",
    "document_draft",
    "document_language",
    "document_policy",
    "previous_session_summary",
    "therapist",
    "transcriber",
    "web_assistant",
)


def _router(logger=None, workload="web_assistant"):
    stem = workload.upper()
    route_env = f"HAYSTACK_LLM_ROUTE_{stem}"
    openai_alias_env = f"HAYSTACK_LITELLM_MODEL_{stem}_OPENAI"
    return LlmWorkloadRouter(
        workload=workload,
        route_env=route_env,
        openai_alias_env=openai_alias_env,
        foundry_alias_env=f"HAYSTACK_LITELLM_MODEL_{stem}_FOUNDRY",
        direct_client=None,
        environ={
            route_env: "litellm_openai",
            openai_alias_env: f"safe-{workload.replace('_', '-')}-alias",
            "LLM_GATEWAY_BASE_URL": "https://gateway.example/v1",
            "HAYSTACK_LLM_GATEWAY_API_KEY": "gateway-secret",
        },
        gateway_client_factory=Mock(return_value=object()),
        event_logger=logger,
    )


def test_production_wiring_builds_routed_clients_for_all_eleven_without_direct_key():
    script = """
import asyncio
import json
import main
from agents.document_agent import get_document_agent
from llm_routing import router_registry

async def noop():
    return None

class Redis:
    async def ping(self):
        return True

main.ui_state_manager.initialize = noop
main.session_manager.initialize = noop
asyncio.run(main.on_startup())
main.ui_state_manager.redis_client = Redis()
main.session_manager.redis_client = Redis()
health = asyncio.run(main.health_check())
print(json.dumps({
    'workloads': router_registry.workloads(),
    'unavailable': router_registry.unavailable_workloads(),
    'routes': {name: router_registry.get(name).target.route.value for name in router_registry.workloads()},
    'models': {name: router_registry.get(name).target.model for name in router_registry.workloads()},
    'documentAgent': get_document_agent() is not None,
    'healthStatus': health.status_code,
    'health': json.loads(health.body),
}))
"""
    environment = os.environ.copy()
    environment.pop("OPENAI_API_KEY", None)
    environment["LLM_GATEWAY_BASE_URL"] = "https://gateway.example/v1"
    environment["HAYSTACK_LLM_GATEWAY_API_KEY"] = "scoped-test-key"
    for workload in WORKLOADS:
        stem = workload.upper()
        environment[f"HAYSTACK_LLM_ROUTE_{stem}"] = "litellm_openai"
        environment[f"HAYSTACK_LITELLM_MODEL_{stem}_OPENAI"] = (
            f"antsa-haystack-{workload.replace('_', '-')}-openai"
        )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    assert result["workloads"] == list(WORKLOADS)
    assert result["unavailable"] == []
    assert set(result["routes"].values()) == {"litellm_openai"}
    assert all(model.startswith("antsa-haystack-") for model in result["models"].values())
    assert result["documentAgent"] is True
    assert result["healthStatus"] == 200
    assert result["health"]["llmRoutes"] == "ready"
    assert result["health"]["documentAgent"] == "ready"
    assert result["health"]["openai"] == "disabled"


def test_readiness_rejects_an_incomplete_router_registry():
    assert set(LlmRouterRegistry().unavailable_workloads()) == ALL_LLM_WORKLOADS


def test_document_endpoint_rejects_incomplete_route_prerequisites():
    from main import generate_document_from_template

    try:
        asyncio.run(
            generate_document_from_template(
                request=None,
                http_request=None,
                authorization=None,
                profileid=None,
            )
        )
    except HTTPException as error:
        assert error.status_code == 503
        assert error.detail == "Document generation models not configured"
    else:
        raise AssertionError("incomplete document routes were accepted")


def test_routed_document_agent_initializes_without_direct_key():
    router = _router()
    target = SimpleNamespace(
        route=LlmRoute.LITELLM_OPENAI,
        workload="document_agent",
        model="safe-document-agent-alias",
        gateway_base_url="https://gateway.example/v1",
        gateway_api_key="gateway-secret",
    )
    agent = DocumentExplorationAgent(None, llm_target=target, llm_router=router)
    generator = agent._create_chat_generator()
    assert isinstance(generator, RoutedOpenAIChatGenerator)
    assert generator.model == "safe-document-agent-alias"


def test_document_agent_sync_generator_path_emits_completion_telemetry():
    logger = Mock()
    router = _router(logger, "document_agent")
    target = SimpleNamespace(
        route=LlmRoute.LITELLM_OPENAI,
        workload="document_agent",
        model="safe-document-agent-alias",
        gateway_base_url="https://gateway.example/v1",
        gateway_api_key="gateway-secret",
    )
    agent = DocumentExplorationAgent(None, llm_target=target, llm_router=router)
    generator = agent._create_agent().chat_generator

    with patch.object(
        OpenAIChatGenerator,
        "run",
        return_value={"replies": []},
    ):
        assert generator.run(messages=[]) == {"replies": []}

    event = json.loads(logger.info.call_args_list[-1].args[0])
    assert event["outcome"] == "success"
    assert event["workload"] == "document_agent"


def test_persona_generator_emits_safe_completion_telemetry():
    logger = Mock()
    router = _router(logger)
    from llm_routing import router_registry

    router_registry.register(router)
    manager = HaystackPipelineManager()
    manager._create_web_assistant_pipeline(
        persona_manager.get_persona(PersonaType.WEB_ASSISTANT)
    )
    generator = manager.pipelines[PersonaType.WEB_ASSISTANT].get_component("generator")
    with patch.object(OpenAIChatGenerator, "run_async", new=AsyncMock(return_value={"replies": []})):
        assert asyncio.run(generator.run_async(messages=[])) == {"replies": []}
    event = json.loads(logger.info.call_args_list[-1].args[0])
    assert event["workload"] == "web_assistant"
    assert event["model"] == "safe-web-assistant-alias"
    assert event["outcome"] == "success"
    assert "gateway-secret" not in json.dumps(event)


def test_persona_nontrusted_sync_path_emits_error_telemetry():
    logger = Mock()
    router = _router(logger)
    from llm_routing import router_registry

    router_registry.register(router)
    manager = HaystackPipelineManager()
    manager._create_web_assistant_pipeline(
        persona_manager.get_persona(PersonaType.WEB_ASSISTANT)
    )
    generator = manager.pipelines[PersonaType.WEB_ASSISTANT].get_component("generator")

    with patch.object(
        OpenAIChatGenerator,
        "run",
        side_effect=RuntimeError("provider failed with sensitive content"),
    ):
        try:
            generator.run(messages=[])
        except RuntimeError:
            pass
        else:
            raise AssertionError("sync provider failure was swallowed")

    event = json.loads(logger.info.call_args_list[-1].args[0])
    assert event["outcome"] == "error"
    assert "sensitive content" not in json.dumps(event)


def test_persona_trusted_async_cancellation_emits_one_aborted_event():
    logger = Mock()
    router = _router(logger)
    generator = RoutedOpenAIChatGenerator(
        llm_router=router,
        model=router.target.model,
        api_base_url="https://gateway.example/v1",
        api_key=Secret.from_token("gateway-secret"),
    )

    with patch.object(
        OpenAIChatGenerator,
        "run_async",
        new=AsyncMock(side_effect=asyncio.CancelledError()),
    ):
        try:
            asyncio.run(generator.run_async(messages=[]))
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("async cancellation was swallowed")

    events = [
        json.loads(call.args[0])
        for call in logger.info.call_args_list
        if "llm_workload_call_completed" in call.args[0]
    ]
    assert len(events) == 1
    assert events[0]["outcome"] == "aborted"


def test_stream_telemetry_records_abort_without_provider_fallback():
    logger = Mock()
    router = _router(logger)

    async def response():
        yield "first"
        raise RuntimeError("upstream stream failed")

    operation = AsyncMock(return_value=response())

    async def consume():
        return [item async for item in router.stream(operation)]

    try:
        asyncio.run(consume())
    except RuntimeError:
        pass
    else:
        raise AssertionError("stream failure was swallowed")
    operation.assert_awaited_once_with(router.target)
    event = json.loads(logger.info.call_args_list[-1].args[0])
    assert event["outcome"] == "error"


def test_release_identity_requires_an_exact_full_sha(monkeypatch, tmp_path):
    monkeypatch.setenv("RELEASE_SHA", "a" * 40)
    assert release_sha() == "a" * 40
    monkeypatch.setenv("RELEASE_SHA", "develop")
    assert release_sha() == "unknown"
