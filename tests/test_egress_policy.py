"""Focused tests for the LLM_EGRESS_POLICY egress restriction."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from llm_routing import (
    CHAT_FOUNDRY_ALIAS_ENV,
    CHAT_ROUTE_ENV,
    CHAT_WORKLOAD,
    EGRESS_POLICY_REQUIRE_GATEWAY,
    EGRESS_POLICY_UNRESTRICTED,
    GATEWAY_BASE_URL_ENV,
    HAYSTACK_GATEWAY_API_KEY_ENV,
    LLM_EGRESS_POLICY_ENV,
    PREVIOUS_SESSION_SUMMARY_FOUNDRY_ALIAS_ENV,
    PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV,
    PREVIOUS_SESSION_SUMMARY_ROUTE_ENV,
    LlmRoute,
    LlmRoutingConfigurationError,
    LlmWorkloadRouter,
    PreviousSessionSummaryRouter,
)


GATEWAY_ENV = {
    GATEWAY_BASE_URL_ENV: "https://gateway.example.com/v1",
    HAYSTACK_GATEWAY_API_KEY_ENV: "gateway-shared-secret",
}

ALIAS_ENV = {
    PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV: (
        "antsa-haystack-previous-session-summary-openai"
    ),
    PREVIOUS_SESSION_SUMMARY_FOUNDRY_ALIAS_ENV: (
        "antsa-haystack-previous-session-summary-foundry"
    ),
    CHAT_FOUNDRY_ALIAS_ENV: "antsa-haystack-chat-foundry",
}


def test_default_unrestricted_keeps_the_direct_openai_route():
    direct_client = object()
    gateway_factory = Mock()

    router = PreviousSessionSummaryRouter(
        direct_client,
        environ={},
        gateway_client_factory=gateway_factory,
    )

    assert router.target.route is LlmRoute.DIRECT_OPENAI
    assert router.target.client is direct_client
    gateway_factory.assert_not_called()

    explicit = PreviousSessionSummaryRouter(
        direct_client,
        environ={LLM_EGRESS_POLICY_ENV: EGRESS_POLICY_UNRESTRICTED},
        gateway_client_factory=Mock(),
    )
    assert explicit.target.route is LlmRoute.DIRECT_OPENAI


@pytest.mark.parametrize(
    ("route_env", "route_env_value", "alias_env", "expected_route"),
    [
        (
            PREVIOUS_SESSION_SUMMARY_ROUTE_ENV,
            "litellm_openai",
            PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV,
            LlmRoute.LITELLM_OPENAI,
        ),
        (
            PREVIOUS_SESSION_SUMMARY_ROUTE_ENV,
            "litellm_foundry",
            PREVIOUS_SESSION_SUMMARY_FOUNDRY_ALIAS_ENV,
            LlmRoute.LITELLM_FOUNDRY,
        ),
        (
            CHAT_ROUTE_ENV,
            "litellm_foundry",
            CHAT_FOUNDRY_ALIAS_ENV,
            LlmRoute.LITELLM_FOUNDRY,
        ),
    ],
)
def test_require_gateway_resolves_the_gateway_route_for_each_workload(
    route_env, route_env_value, alias_env, expected_route
):
    gateway_client = object()
    gateway_factory = Mock(return_value=gateway_client)
    environ = {
        LLM_EGRESS_POLICY_ENV: EGRESS_POLICY_REQUIRE_GATEWAY,
        route_env: route_env_value,
        **GATEWAY_ENV,
        alias_env: ALIAS_ENV[alias_env],
    }

    if route_env == PREVIOUS_SESSION_SUMMARY_ROUTE_ENV:
        router = PreviousSessionSummaryRouter(
            object(), environ=environ, gateway_client_factory=gateway_factory
        )
    else:
        router = LlmWorkloadRouter(
            workload=CHAT_WORKLOAD,
            route_env=route_env,
            openai_alias_env="HAYSTACK_LITELLM_MODEL_CHAT_OPENAI",
            foundry_alias_env=CHAT_FOUNDRY_ALIAS_ENV,
            direct_client=object(),
            environ=environ,
            gateway_client_factory=gateway_factory,
        )

    assert router.target.route is expected_route
    assert router.target.client is gateway_client
    assert router.target.gateway_base_url == (
        GATEWAY_ENV[GATEWAY_BASE_URL_ENV].rstrip("/")
    )
    gateway_factory.assert_called_once()


def test_require_gateway_defaults_an_unset_route_to_the_gateway():
    gateway_factory = Mock(return_value=object())

    router = PreviousSessionSummaryRouter(
        object(),
        environ={
            LLM_EGRESS_POLICY_ENV: EGRESS_POLICY_REQUIRE_GATEWAY,
            **GATEWAY_ENV,
            PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV: (
                ALIAS_ENV[PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV]
            ),
        },
        gateway_client_factory=gateway_factory,
    )

    assert router.target.route is LlmRoute.LITELLM_OPENAI
    gateway_factory.assert_called_once()


@pytest.mark.parametrize(
    ("environ", "missing_var"),
    [
        (
            {
                LLM_EGRESS_POLICY_ENV: EGRESS_POLICY_REQUIRE_GATEWAY,
                PREVIOUS_SESSION_SUMMARY_ROUTE_ENV: "litellm_openai",
                HAYSTACK_GATEWAY_API_KEY_ENV: "gateway-shared-secret",
                PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV: (
                    ALIAS_ENV[PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV]
                ),
            },
            GATEWAY_BASE_URL_ENV,
        ),
        (
            {
                LLM_EGRESS_POLICY_ENV: EGRESS_POLICY_REQUIRE_GATEWAY,
                PREVIOUS_SESSION_SUMMARY_ROUTE_ENV: "litellm_openai",
                GATEWAY_BASE_URL_ENV: "https://gateway.example.com/v1",
                PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV: (
                    ALIAS_ENV[PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV]
                ),
            },
            HAYSTACK_GATEWAY_API_KEY_ENV,
        ),
        (
            {
                LLM_EGRESS_POLICY_ENV: EGRESS_POLICY_REQUIRE_GATEWAY,
                PREVIOUS_SESSION_SUMMARY_ROUTE_ENV: "litellm_openai",
                **GATEWAY_ENV,
            },
            PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV,
        ),
    ],
)
def test_require_gateway_with_incomplete_env_raises_before_any_client(
    environ, missing_var
):
    gateway_factory = Mock()

    with pytest.raises(LlmRoutingConfigurationError) as raised:
        PreviousSessionSummaryRouter(
            object(),
            environ=environ,
            gateway_client_factory=gateway_factory,
        )

    assert missing_var in str(raised.value)
    gateway_factory.assert_not_called()


def test_require_gateway_rejects_an_explicit_direct_route():
    gateway_factory = Mock()

    with pytest.raises(LlmRoutingConfigurationError) as raised:
        PreviousSessionSummaryRouter(
            object(),
            environ={
                LLM_EGRESS_POLICY_ENV: EGRESS_POLICY_REQUIRE_GATEWAY,
                PREVIOUS_SESSION_SUMMARY_ROUTE_ENV: "direct_openai",
                **GATEWAY_ENV,
                **ALIAS_ENV,
            },
            gateway_client_factory=gateway_factory,
        )

    message = str(raised.value)
    assert LLM_EGRESS_POLICY_ENV in message
    assert PREVIOUS_SESSION_SUMMARY_ROUTE_ENV in message
    gateway_factory.assert_not_called()


def test_unknown_egress_policy_value_is_rejected():
    with pytest.raises(LlmRoutingConfigurationError) as raised:
        PreviousSessionSummaryRouter(
            object(),
            environ={LLM_EGRESS_POLICY_ENV: "au_only"},
            gateway_client_factory=Mock(),
        )

    assert LLM_EGRESS_POLICY_ENV in str(raised.value)
