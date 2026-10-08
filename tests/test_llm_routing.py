"""Focused tests for the server-controlled per-workload LLM routers."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, Mock

import pytest

from llm_routing import (
    CHAT_OPENAI_ALIAS_ENV,
    CHAT_ROUTE_ENV,
    CHAT_WORKLOAD,
    COMPANION_ROUTE_ENV,
    DOCUMENT_AGENT_ROUTE_ENV,
    DOCUMENT_DRAFT_DIRECT_MODEL,
    DOCUMENT_DRAFT_OPENAI_ALIAS_ENV,
    DOCUMENT_DRAFT_ROUTE_ENV,
    DOCUMENT_DRAFT_WORKLOAD,
    DOCUMENT_LANGUAGE_FOUNDRY_ALIAS_ENV,
    DOCUMENT_LANGUAGE_ROUTE_ENV,
    DOCUMENT_LANGUAGE_WORKLOAD,
    DOCUMENT_POLICY_DIRECT_MODEL,
    DOCUMENT_POLICY_ROUTE_ENV,
    DOCUMENT_POLICY_WORKLOAD,
    HAYSTACK_GATEWAY_API_KEY_ENV,
    PREVIOUS_SESSION_SUMMARY_DIRECT_MODEL,
    PREVIOUS_SESSION_SUMMARY_FOUNDRY_ALIAS_ENV,
    PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV,
    PREVIOUS_SESSION_SUMMARY_ROUTE_ENV,
    THERAPIST_ROUTE_ENV,
    TRANSCRIBER_ROUTE_ENV,
    WEB_ASSISTANT_OPENAI_ALIAS_ENV,
    WEB_ASSISTANT_ROUTE_ENV,
    GATEWAY_BASE_URL_ENV,
    LlmRoute,
    LlmRoutingConfigurationError,
    LlmRouterRegistry,
    LlmWorkloadRouter,
    PreviousSessionSummaryRouter,
)


def test_direct_openai_is_the_default_and_preserves_the_existing_model():
    direct_client = object()
    gateway_factory = Mock()

    router = PreviousSessionSummaryRouter(
        direct_client,
        environ={},
        gateway_client_factory=gateway_factory,
    )

    assert router.target.route is LlmRoute.DIRECT_OPENAI
    assert router.target.model == PREVIOUS_SESSION_SUMMARY_DIRECT_MODEL
    assert router.target.client is direct_client
    gateway_factory.assert_not_called()


@pytest.mark.parametrize(
    ("route", "alias_env", "alias"),
    [
        (
            LlmRoute.LITELLM_OPENAI,
            PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV,
            "antsa-haystack-previous-session-summary-openai",
        ),
        (
            LlmRoute.LITELLM_FOUNDRY,
            PREVIOUS_SESSION_SUMMARY_FOUNDRY_ALIAS_ENV,
            "antsa-haystack-previous-session-summary-foundry",
        ),
    ],
)
def test_gateway_routes_use_only_the_haystack_key_and_selected_alias(
    route, alias_env, alias
):
    gateway_client = object()
    gateway_factory = Mock(return_value=gateway_client)
    environ = {
        PREVIOUS_SESSION_SUMMARY_ROUTE_ENV: route.value,
        GATEWAY_BASE_URL_ENV: "https://private-gateway.example/v1",
        HAYSTACK_GATEWAY_API_KEY_ENV: "haystack-dedicated-key",
        alias_env: alias,
        "LLM_GATEWAY_API_KEY": "api-service-key-must-not-be-used",
        "OPENAI_API_KEY": "direct-key-must-not-be-used",
    }

    router = PreviousSessionSummaryRouter(
        object(),
        environ=environ,
        gateway_client_factory=gateway_factory,
    )

    assert router.target.route is route
    assert router.target.model == alias
    assert router.target.client is gateway_client
    gateway_factory.assert_called_once_with(
        api_key="haystack-dedicated-key",
        base_url="https://private-gateway.example/v1",
    )


@pytest.mark.parametrize(
    "route",
    [LlmRoute.LITELLM_OPENAI.value, LlmRoute.LITELLM_FOUNDRY.value],
)
def test_selected_gateway_route_requires_its_dedicated_key(route):
    alias_env = (
        PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV
        if route == LlmRoute.LITELLM_OPENAI.value
        else PREVIOUS_SESSION_SUMMARY_FOUNDRY_ALIAS_ENV
    )
    environ = {
        PREVIOUS_SESSION_SUMMARY_ROUTE_ENV: route,
        GATEWAY_BASE_URL_ENV: "https://private-gateway.example/v1",
        alias_env: "configured-alias",
        "LLM_GATEWAY_API_KEY": "api-service-key-is-not-a-fallback",
        "OPENAI_API_KEY": "direct-key-is-not-a-fallback",
    }

    with pytest.raises(
        LlmRoutingConfigurationError,
        match=HAYSTACK_GATEWAY_API_KEY_ENV,
    ):
        PreviousSessionSummaryRouter(object(), environ=environ)


@pytest.mark.parametrize(
    ("missing_env", "route"),
    [
        (GATEWAY_BASE_URL_ENV, LlmRoute.LITELLM_OPENAI),
        (PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV, LlmRoute.LITELLM_OPENAI),
        (PREVIOUS_SESSION_SUMMARY_FOUNDRY_ALIAS_ENV, LlmRoute.LITELLM_FOUNDRY),
    ],
)
def test_selected_gateway_route_rejects_missing_configuration(missing_env, route):
    environ = {
        PREVIOUS_SESSION_SUMMARY_ROUTE_ENV: route.value,
        GATEWAY_BASE_URL_ENV: "https://private-gateway.example/v1",
        HAYSTACK_GATEWAY_API_KEY_ENV: "haystack-dedicated-key",
        PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV: "openai-alias",
        PREVIOUS_SESSION_SUMMARY_FOUNDRY_ALIAS_ENV: "foundry-alias",
    }
    del environ[missing_env]

    with pytest.raises(LlmRoutingConfigurationError, match=missing_env):
        PreviousSessionSummaryRouter(object(), environ=environ)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://private-gateway.example",
        "https://private-gateway.example/v1?destination=other",
        "https://user:password@private-gateway.example/v1",
        "http://private-gateway.example/v1",
    ],
)
def test_gateway_url_is_restricted_without_echoing_its_value(base_url):
    environ = {
        PREVIOUS_SESSION_SUMMARY_ROUTE_ENV: LlmRoute.LITELLM_OPENAI.value,
        GATEWAY_BASE_URL_ENV: base_url,
        HAYSTACK_GATEWAY_API_KEY_ENV: "haystack-dedicated-key",
        PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV: "openai-alias",
    }

    with pytest.raises(LlmRoutingConfigurationError) as caught:
        PreviousSessionSummaryRouter(object(), environ=environ)

    assert base_url not in str(caught.value)


def test_invalid_route_is_rejected_without_creating_a_client():
    gateway_factory = Mock()

    with pytest.raises(LlmRoutingConfigurationError, match="must be one of"):
        PreviousSessionSummaryRouter(
            object(),
            environ={PREVIOUS_SESSION_SUMMARY_ROUTE_ENV: "request_override"},
            gateway_client_factory=gateway_factory,
        )

    gateway_factory.assert_not_called()


@pytest.mark.parametrize(
    "alias",
    ["alias with spaces", "alias\nforged-event", "?provider=other", "a" * 201],
)
def test_selected_model_alias_must_be_a_stable_safe_value(alias):
    environ = {
        PREVIOUS_SESSION_SUMMARY_ROUTE_ENV: LlmRoute.LITELLM_OPENAI.value,
        GATEWAY_BASE_URL_ENV: "https://private-gateway.example/v1",
        HAYSTACK_GATEWAY_API_KEY_ENV: "haystack-dedicated-key",
        PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV: alias,
    }

    with pytest.raises(
        LlmRoutingConfigurationError,
        match=PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV,
    ):
        PreviousSessionSummaryRouter(object(), environ=environ)


def test_call_telemetry_contains_only_safe_route_outcome_metadata():
    logger = Mock()
    gateway_factory = Mock(return_value=object())
    environ = {
        PREVIOUS_SESSION_SUMMARY_ROUTE_ENV: LlmRoute.LITELLM_OPENAI.value,
        GATEWAY_BASE_URL_ENV: "https://sensitive-gateway-host.example/v1",
        HAYSTACK_GATEWAY_API_KEY_ENV: "sensitive-haystack-key",
        PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV: "safe-workload-alias",
    }
    router = PreviousSessionSummaryRouter(
        object(),
        environ=environ,
        gateway_client_factory=gateway_factory,
        event_logger=logger,
    )
    operation = AsyncMock(return_value="summary-result")

    result = asyncio.run(router.execute(operation))

    assert result == "summary-result"
    operation.assert_awaited_once_with(router.target)
    events = [json.loads(call.args[0]) for call in logger.info.call_args_list]
    assert events[0] == {
        "event": "llm_workload_route_configured",
        "model": "safe-workload-alias",
        "route": "litellm_openai",
        "workload": "previous_session_summary",
    }
    assert events[1]["event"] == "llm_workload_call_completed"
    assert events[1]["outcome"] == "success"
    assert isinstance(events[1]["latencyMs"], int)
    serialized_events = json.dumps(events)
    assert "sensitive-gateway-host" not in serialized_events
    assert "sensitive-haystack-key" not in serialized_events
    assert "summary-result" not in serialized_events


def test_error_telemetry_does_not_log_exception_details():
    logger = Mock()
    router = PreviousSessionSummaryRouter(
        object(),
        environ={},
        event_logger=logger,
    )

    async def fail(_target):
        raise RuntimeError("sensitive transcript and session identifier")

    with pytest.raises(RuntimeError, match="sensitive transcript"):
        asyncio.run(router.execute(fail))

    event = json.loads(logger.info.call_args_list[-1].args[0])
    assert event["outcome"] == "error"
    assert "sensitive" not in json.dumps(event)


def _make_general_router(
    workload,
    route_env,
    openai_alias_env,
    foundry_alias_env,
    *,
    direct_model=None,
    direct_client=None,
    environ=None,
    gateway_client_factory=None,
    event_logger=None,
):
    kwargs = {}
    if direct_model is not None:
        kwargs["direct_model"] = direct_model
    if environ is not None:
        kwargs["environ"] = environ
    if gateway_client_factory is not None:
        kwargs["gateway_client_factory"] = gateway_client_factory
    if event_logger is not None:
        kwargs["event_logger"] = event_logger
    return LlmWorkloadRouter(
        workload=workload,
        route_env=route_env,
        openai_alias_env=openai_alias_env,
        foundry_alias_env=foundry_alias_env,
        direct_client=direct_client,
        **kwargs,
    )


def test_direct_route_for_pinned_model_workload_uses_its_own_model_and_client():
    direct_client = object()
    gateway_factory = Mock()

    router = _make_general_router(
        DOCUMENT_POLICY_WORKLOAD,
        DOCUMENT_POLICY_ROUTE_ENV,
        "HAYSTACK_LITELLM_MODEL_DOCUMENT_POLICY_OPENAI",
        "HAYSTACK_LITELLM_MODEL_DOCUMENT_POLICY_FOUNDRY",
        direct_model=DOCUMENT_POLICY_DIRECT_MODEL,
        direct_client=direct_client,
        environ={},
        gateway_client_factory=gateway_factory,
    )

    assert router.target.workload == DOCUMENT_POLICY_WORKLOAD
    assert router.target.route is LlmRoute.DIRECT_OPENAI
    assert router.target.model == DOCUMENT_POLICY_DIRECT_MODEL
    assert router.target.client is direct_client
    assert router.target.gateway_base_url is None
    assert router.target.gateway_api_key is None
    gateway_factory.assert_not_called()


def test_direct_route_without_pinned_model_omits_model_from_telemetry():
    logger = Mock()
    gateway_factory = Mock()

    router = _make_general_router(
        CHAT_WORKLOAD,
        CHAT_ROUTE_ENV,
        CHAT_OPENAI_ALIAS_ENV,
        "HAYSTACK_LITELLM_MODEL_CHAT_FOUNDRY",
        direct_client=object(),
        environ={},
        gateway_client_factory=gateway_factory,
        event_logger=logger,
    )

    assert router.target.route is LlmRoute.DIRECT_OPENAI
    assert router.target.model == ""
    operation = AsyncMock(return_value="chat-result")
    result = asyncio.run(router.execute(operation))
    assert result == "chat-result"

    events = [json.loads(call.args[0]) for call in logger.info.call_args_list]
    assert events[0] == {
        "event": "llm_workload_route_configured",
        "route": "direct_openai",
        "workload": CHAT_WORKLOAD,
    }
    assert events[1]["event"] == "llm_workload_call_completed"
    assert events[1]["outcome"] == "success"
    assert "model" not in events[0]
    assert "model" not in events[1]


def test_route_env_namespacing_only_reroutes_the_configured_workload():
    gateway_client = object()
    gateway_factory = Mock(return_value=gateway_client)
    direct_client = object()
    environ = {
        DOCUMENT_DRAFT_ROUTE_ENV: LlmRoute.LITELLM_OPENAI.value,
        GATEWAY_BASE_URL_ENV: "https://private-gateway.example/v1",
        HAYSTACK_GATEWAY_API_KEY_ENV: "test-gateway-key",
        DOCUMENT_DRAFT_OPENAI_ALIAS_ENV: "antsa-haystack-document-draft-openai",
    }

    draft_router = _make_general_router(
        DOCUMENT_DRAFT_WORKLOAD,
        DOCUMENT_DRAFT_ROUTE_ENV,
        DOCUMENT_DRAFT_OPENAI_ALIAS_ENV,
        "HAYSTACK_LITELLM_MODEL_DOCUMENT_DRAFT_FOUNDRY",
        direct_model=DOCUMENT_DRAFT_DIRECT_MODEL,
        direct_client=direct_client,
        environ=environ,
        gateway_client_factory=gateway_factory,
    )
    policy_router = _make_general_router(
        DOCUMENT_POLICY_WORKLOAD,
        DOCUMENT_POLICY_ROUTE_ENV,
        "HAYSTACK_LITELLM_MODEL_DOCUMENT_POLICY_OPENAI",
        "HAYSTACK_LITELLM_MODEL_DOCUMENT_POLICY_FOUNDRY",
        direct_model=DOCUMENT_POLICY_DIRECT_MODEL,
        direct_client=direct_client,
        environ=environ,
        gateway_client_factory=gateway_factory,
    )
    chat_router = _make_general_router(
        CHAT_WORKLOAD,
        CHAT_ROUTE_ENV,
        CHAT_OPENAI_ALIAS_ENV,
        "HAYSTACK_LITELLM_MODEL_CHAT_FOUNDRY",
        direct_client=direct_client,
        environ=environ,
        gateway_client_factory=gateway_factory,
    )

    assert draft_router.target.route is LlmRoute.LITELLM_OPENAI
    assert draft_router.target.model == "antsa-haystack-document-draft-openai"
    assert draft_router.target.client is gateway_client

    assert policy_router.target.route is LlmRoute.DIRECT_OPENAI
    assert policy_router.target.model == DOCUMENT_POLICY_DIRECT_MODEL

    assert chat_router.target.route is LlmRoute.DIRECT_OPENAI
    assert chat_router.target.model == ""

    gateway_factory.assert_called_once()


@pytest.mark.parametrize(
    ("route_env", "foundry_alias_env"),
    [
        (
            DOCUMENT_LANGUAGE_ROUTE_ENV,
            DOCUMENT_LANGUAGE_FOUNDRY_ALIAS_ENV,
        ),
        (
            DOCUMENT_DRAFT_ROUTE_ENV,
            "HAYSTACK_LITELLM_MODEL_DOCUMENT_DRAFT_FOUNDRY",
        ),
    ],
)
def test_foundry_route_populates_gateway_fields_for_pinned_workloads(
    route_env, foundry_alias_env
):
    gateway_client = object()
    gateway_factory = Mock(return_value=gateway_client)
    environ = {
        route_env: LlmRoute.LITELLM_FOUNDRY.value,
        GATEWAY_BASE_URL_ENV: "https://private-gateway.example/v1",
        HAYSTACK_GATEWAY_API_KEY_ENV: "test-gateway-key",
        foundry_alias_env: "antsa-haystack-foundry-alias",
    }

    router = _make_general_router(
        DOCUMENT_LANGUAGE_WORKLOAD if route_env is DOCUMENT_LANGUAGE_ROUTE_ENV
        else DOCUMENT_DRAFT_WORKLOAD,
        route_env,
        "HAYSTACK_LITELLM_MODEL_DOCUMENT_LANGUAGE_OPENAI"
        if route_env is DOCUMENT_LANGUAGE_ROUTE_ENV
        else DOCUMENT_DRAFT_OPENAI_ALIAS_ENV,
        foundry_alias_env,
        direct_model=(
            "gpt-5.4-mini"
            if route_env is DOCUMENT_LANGUAGE_ROUTE_ENV
            else DOCUMENT_DRAFT_DIRECT_MODEL
        ),
        direct_client=object(),
        environ=environ,
        gateway_client_factory=gateway_factory,
    )

    assert router.target.route is LlmRoute.LITELLM_FOUNDRY
    assert router.target.model == "antsa-haystack-foundry-alias"
    assert router.target.client is gateway_client
    assert router.target.gateway_base_url == "https://private-gateway.example/v1"
    assert router.target.gateway_api_key == "test-gateway-key"
    gateway_factory.assert_called_once_with(
        api_key="test-gateway-key",
        base_url="https://private-gateway.example/v1",
    )


@pytest.mark.parametrize(
    ("route_env", "openai_alias_env"),
    [
        (
            WEB_ASSISTANT_ROUTE_ENV,
            WEB_ASSISTANT_OPENAI_ALIAS_ENV,
        ),
        (
            THERAPIST_ROUTE_ENV,
            "HAYSTACK_LITELLM_MODEL_THERAPIST_OPENAI",
        ),
        (
            COMPANION_ROUTE_ENV,
            "HAYSTACK_LITELLM_MODEL_COMPANION_OPENAI",
        ),
        (
            TRANSCRIBER_ROUTE_ENV,
            "HAYSTACK_LITELLM_MODEL_TRANSCRIBER_OPENAI",
        ),
        (
            DOCUMENT_AGENT_ROUTE_ENV,
            "HAYSTACK_LITELLM_MODEL_DOCUMENT_AGENT_OPENAI",
        ),
    ],
)
def test_misconfigured_general_litellm_route_names_only_its_own_workload(
    route_env, openai_alias_env
):
    gateway_factory = Mock()
    environ = {
        route_env: LlmRoute.LITELLM_OPENAI.value,
        HAYSTACK_GATEWAY_API_KEY_ENV: "test-gateway-key",
    }

    with pytest.raises(LlmRoutingConfigurationError) as caught:
        _make_general_router(
            route_env.removeprefix("HAYSTACK_LLM_ROUTE_").lower(),
            route_env,
            openai_alias_env,
            openai_alias_env.replace("_OPENAI", "_FOUNDRY"),
            direct_client=object(),
            environ=environ,
            gateway_client_factory=gateway_factory,
        )

    message = str(caught.value)
    assert f"when {route_env}=litellm_openai" in message
    assert WEB_ASSISTANT_ROUTE_ENV not in message or route_env == WEB_ASSISTANT_ROUTE_ENV
    assert THERAPIST_ROUTE_ENV not in message or route_env == THERAPIST_ROUTE_ENV
    assert COMPANION_ROUTE_ENV not in message or route_env == COMPANION_ROUTE_ENV
    assert (
        TRANSCRIBER_ROUTE_ENV not in message or route_env == TRANSCRIBER_ROUTE_ENV
    )
    assert (
        DOCUMENT_AGENT_ROUTE_ENV not in message
        or route_env == DOCUMENT_AGENT_ROUTE_ENV
    )
    gateway_factory.assert_not_called()


def test_registry_roundtrips_routers_by_workload():
    registry = LlmRouterRegistry()
    policy_router = _make_general_router(
        DOCUMENT_POLICY_WORKLOAD,
        DOCUMENT_POLICY_ROUTE_ENV,
        "HAYSTACK_LITELLM_MODEL_DOCUMENT_POLICY_OPENAI",
        "HAYSTACK_LITELLM_MODEL_DOCUMENT_POLICY_FOUNDRY",
        direct_model=DOCUMENT_POLICY_DIRECT_MODEL,
        direct_client=object(),
        environ={},
    )
    chat_router = _make_general_router(
        CHAT_WORKLOAD,
        CHAT_ROUTE_ENV,
        CHAT_OPENAI_ALIAS_ENV,
        "HAYSTACK_LITELLM_MODEL_CHAT_FOUNDRY",
        direct_client=object(),
        environ={},
    )

    registry.register(policy_router)
    registry.register(chat_router)

    assert registry.get(DOCUMENT_POLICY_WORKLOAD) is policy_router
    assert registry.get(CHAT_WORKLOAD) is chat_router


def test_registry_duplicate_registration_replaces_previous_router():
    registry = LlmRouterRegistry()
    first = _make_general_router(
        DOCUMENT_POLICY_WORKLOAD,
        DOCUMENT_POLICY_ROUTE_ENV,
        "HAYSTACK_LITELLM_MODEL_DOCUMENT_POLICY_OPENAI",
        "HAYSTACK_LITELLM_MODEL_DOCUMENT_POLICY_FOUNDRY",
        direct_model=DOCUMENT_POLICY_DIRECT_MODEL,
        direct_client=object(),
        environ={},
    )
    replacement = _make_general_router(
        DOCUMENT_POLICY_WORKLOAD,
        DOCUMENT_POLICY_ROUTE_ENV,
        "HAYSTACK_LITELLM_MODEL_DOCUMENT_POLICY_OPENAI",
        "HAYSTACK_LITELLM_MODEL_DOCUMENT_POLICY_FOUNDRY",
        direct_model=DOCUMENT_POLICY_DIRECT_MODEL,
        direct_client=object(),
        environ={},
    )

    registry.register(first)
    registry.register(replacement)

    assert registry.get(DOCUMENT_POLICY_WORKLOAD) is replacement


def test_registry_unknown_workload_raises_error_naming_it():
    registry = LlmRouterRegistry()

    with pytest.raises(RuntimeError) as caught:
        registry.get(DOCUMENT_POLICY_WORKLOAD)

    assert DOCUMENT_POLICY_WORKLOAD in str(caught.value)


def test_registry_module_level_instance_is_available():
    from llm_routing import router_registry

    assert isinstance(router_registry, LlmRouterRegistry)


def test_gateway_compatibility_is_explicit_without_changing_direct_calls():
    from dataclasses import replace
    from llm_routing import gateway_chat_compatibility

    direct = _make_general_router(
        CHAT_WORKLOAD,
        CHAT_ROUTE_ENV,
        CHAT_OPENAI_ALIAS_ENV,
        "HAYSTACK_LITELLM_MODEL_CHAT_FOUNDRY",
        direct_client=object(),
        environ={},
    )
    gateway = _make_general_router(
        CHAT_WORKLOAD,
        CHAT_ROUTE_ENV,
        CHAT_OPENAI_ALIAS_ENV,
        "HAYSTACK_LITELLM_MODEL_CHAT_FOUNDRY",
        direct_client=None,
        environ={
            CHAT_ROUTE_ENV: "litellm_openai",
            CHAT_OPENAI_ALIAS_ENV: "antsa-haystack-chat-openai",
            GATEWAY_BASE_URL_ENV: "https://gateway.example/v1",
            HAYSTACK_GATEWAY_API_KEY_ENV: "scoped-key",
        },
        gateway_client_factory=Mock(return_value=object()),
    )

    assert gateway_chat_compatibility(direct.target) == {}
    assert gateway_chat_compatibility(gateway.target) == {"reasoning_effort": "none"}
    assert gateway_chat_compatibility(replace(gateway.target, route=LlmRoute.LITELLM_FOUNDRY)) == {}


def test_general_router_telemetry_never_contains_gateway_secrets_or_payloads():
    logger = Mock()
    gateway_factory = Mock(return_value=object())
    environ = {
        DOCUMENT_POLICY_ROUTE_ENV: LlmRoute.LITELLM_FOUNDRY.value,
        GATEWAY_BASE_URL_ENV: "https://sensitive-gateway-host.example/v1",
        HAYSTACK_GATEWAY_API_KEY_ENV: "sensitive-test-gateway-key",
        "HAYSTACK_LITELLM_MODEL_DOCUMENT_POLICY_FOUNDRY": "safe-policy-alias",
    }
    router = _make_general_router(
        DOCUMENT_POLICY_WORKLOAD,
        DOCUMENT_POLICY_ROUTE_ENV,
        "HAYSTACK_LITELLM_MODEL_DOCUMENT_POLICY_OPENAI",
        "HAYSTACK_LITELLM_MODEL_DOCUMENT_POLICY_FOUNDRY",
        direct_model=DOCUMENT_POLICY_DIRECT_MODEL,
        direct_client=object(),
        environ=environ,
        gateway_client_factory=gateway_factory,
        event_logger=logger,
    )
    sensitive_result = {
        "policy_text": "sensitive client transcript payload must not be logged"
    }
    operation = AsyncMock(return_value=sensitive_result)

    result = asyncio.run(router.execute(operation))

    assert result is sensitive_result
    operation.assert_awaited_once_with(router.target)
    events = [json.loads(call.args[0]) for call in logger.info.call_args_list]
    assert events[0] == {
        "event": "llm_workload_route_configured",
        "model": "safe-policy-alias",
        "route": "litellm_foundry",
        "workload": DOCUMENT_POLICY_WORKLOAD,
    }
    assert events[1]["event"] == "llm_workload_call_completed"
    assert events[1]["outcome"] == "success"
    assert isinstance(events[1]["latencyMs"], int)
    serialized_events = json.dumps(events)
    assert "sensitive-gateway-host" not in serialized_events
    assert "sensitive-test-gateway-key" not in serialized_events
    assert "sensitive client transcript" not in serialized_events
    assert router.target.gateway_base_url not in serialized_events
    assert router.target.gateway_api_key not in serialized_events


def test_general_router_error_telemetry_excludes_secrets_and_exception_details():
    logger = Mock()
    environ = {
        DOCUMENT_POLICY_ROUTE_ENV: LlmRoute.LITELLM_FOUNDRY.value,
        GATEWAY_BASE_URL_ENV: "https://sensitive-gateway-host.example/v1",
        HAYSTACK_GATEWAY_API_KEY_ENV: "sensitive-test-gateway-key",
        "HAYSTACK_LITELLM_MODEL_DOCUMENT_POLICY_FOUNDRY": "safe-policy-alias",
    }
    router = _make_general_router(
        DOCUMENT_POLICY_WORKLOAD,
        DOCUMENT_POLICY_ROUTE_ENV,
        "HAYSTACK_LITELLM_MODEL_DOCUMENT_POLICY_OPENAI",
        "HAYSTACK_LITELLM_MODEL_DOCUMENT_POLICY_FOUNDRY",
        direct_model=DOCUMENT_POLICY_DIRECT_MODEL,
        direct_client=object(),
        environ=environ,
        gateway_client_factory=Mock(return_value=object()),
        event_logger=logger,
    )

    async def fail(_target):
        raise RuntimeError("sensitive policy evaluation failure")

    with pytest.raises(RuntimeError, match="sensitive policy"):
        asyncio.run(router.execute(fail))

    events = [json.loads(call.args[0]) for call in logger.info.call_args_list]
    error_event = events[-1]
    assert error_event["event"] == "llm_workload_call_completed"
    assert error_event["outcome"] == "error"
    serialized_events = json.dumps(events)
    assert "sensitive-gateway-host" not in serialized_events
    assert "sensitive-test-gateway-key" not in serialized_events
    assert "sensitive policy evaluation" not in serialized_events
