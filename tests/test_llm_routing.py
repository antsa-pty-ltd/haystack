"""Focused tests for the isolated previous-session summary router."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, Mock

import pytest

from llm_routing import (
    HAYSTACK_GATEWAY_API_KEY_ENV,
    PREVIOUS_SESSION_SUMMARY_DIRECT_MODEL,
    PREVIOUS_SESSION_SUMMARY_FOUNDRY_ALIAS_ENV,
    PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV,
    PREVIOUS_SESSION_SUMMARY_ROUTE_ENV,
    GATEWAY_BASE_URL_ENV,
    LlmRoute,
    LlmRoutingConfigurationError,
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
