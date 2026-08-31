"""Server-controlled routing for isolated Haystack LLM workloads."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Mapping, Optional
from urllib.parse import urlsplit

from openai import AsyncOpenAI


PREVIOUS_SESSION_SUMMARY_WORKLOAD = "previous_session_summary"
PREVIOUS_SESSION_SUMMARY_DIRECT_MODEL = "gpt-5.4-mini"
PREVIOUS_SESSION_SUMMARY_ROUTE_ENV = (
    "HAYSTACK_LLM_ROUTE_PREVIOUS_SESSION_SUMMARY"
)
PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV = (
    "HAYSTACK_LITELLM_MODEL_PREVIOUS_SESSION_SUMMARY_OPENAI"
)
PREVIOUS_SESSION_SUMMARY_FOUNDRY_ALIAS_ENV = (
    "HAYSTACK_LITELLM_MODEL_PREVIOUS_SESSION_SUMMARY_FOUNDRY"
)
GATEWAY_BASE_URL_ENV = "LLM_GATEWAY_BASE_URL"
HAYSTACK_GATEWAY_API_KEY_ENV = "HAYSTACK_LLM_GATEWAY_API_KEY"
MODEL_ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


class LlmRoute(str, Enum):
    DIRECT_OPENAI = "direct_openai"
    LITELLM_OPENAI = "litellm_openai"
    LITELLM_FOUNDRY = "litellm_foundry"


class LlmRoutingConfigurationError(ValueError):
    """Raised when a selected, server-controlled route is not configured."""


@dataclass(frozen=True)
class LlmTarget:
    workload: str
    route: LlmRoute
    model: str
    client: Any


GatewayClientFactory = Callable[..., Any]
TargetOperation = Callable[[LlmTarget], Awaitable[Any]]


class PreviousSessionSummaryRouter:
    """Resolve and observe only the durable previous-session summary call."""

    def __init__(
        self,
        direct_client: Any,
        *,
        environ: Optional[Mapping[str, str]] = None,
        gateway_client_factory: GatewayClientFactory = AsyncOpenAI,
        event_logger: Optional[logging.Logger] = None,
    ) -> None:
        self._environ = os.environ if environ is None else environ
        self._event_logger = event_logger or logging.getLogger(__name__)
        self._target = self._resolve_target(
            direct_client=direct_client,
            gateway_client_factory=gateway_client_factory,
        )
        self._emit_safe_event(
            "llm_workload_route_configured",
            route=self._target.route.value,
            model=self._target.model,
        )

    @property
    def target(self) -> LlmTarget:
        return self._target

    async def execute(self, operation: TargetOperation) -> Any:
        """Run one selected call and emit payload-free outcome telemetry."""
        started_at = time.perf_counter()
        try:
            result = await operation(self._target)
        except Exception:
            self._emit_safe_event(
                "llm_workload_call_completed",
                route=self._target.route.value,
                model=self._target.model,
                outcome="error",
                latencyMs=_elapsed_milliseconds(started_at),
            )
            raise

        self._emit_safe_event(
            "llm_workload_call_completed",
            route=self._target.route.value,
            model=self._target.model,
            outcome="success",
            latencyMs=_elapsed_milliseconds(started_at),
        )
        return result

    def _resolve_target(
        self,
        *,
        direct_client: Any,
        gateway_client_factory: GatewayClientFactory,
    ) -> LlmTarget:
        route_value = self._optional_env(
            PREVIOUS_SESSION_SUMMARY_ROUTE_ENV
        ) or LlmRoute.DIRECT_OPENAI.value
        try:
            route = LlmRoute(route_value)
        except ValueError as error:
            allowed_routes = ", ".join(route.value for route in LlmRoute)
            raise LlmRoutingConfigurationError(
                f"{PREVIOUS_SESSION_SUMMARY_ROUTE_ENV} must be one of: "
                f"{allowed_routes}"
            ) from error

        if route is LlmRoute.DIRECT_OPENAI:
            return LlmTarget(
                workload=PREVIOUS_SESSION_SUMMARY_WORKLOAD,
                route=route,
                model=PREVIOUS_SESSION_SUMMARY_DIRECT_MODEL,
                client=direct_client,
            )

        base_url = _validate_gateway_base_url(
            self._required_env(GATEWAY_BASE_URL_ENV, route)
        )
        gateway_api_key = self._required_env(
            HAYSTACK_GATEWAY_API_KEY_ENV, route
        )
        alias_env = (
            PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV
            if route is LlmRoute.LITELLM_OPENAI
            else PREVIOUS_SESSION_SUMMARY_FOUNDRY_ALIAS_ENV
        )
        model_alias = _validate_model_alias(
            self._required_env(alias_env, route), alias_env
        )
        gateway_client = gateway_client_factory(
            api_key=gateway_api_key,
            base_url=base_url,
        )
        return LlmTarget(
            workload=PREVIOUS_SESSION_SUMMARY_WORKLOAD,
            route=route,
            model=model_alias,
            client=gateway_client,
        )

    def _optional_env(self, name: str) -> str:
        return (self._environ.get(name) or "").strip()

    def _required_env(self, name: str, route: LlmRoute) -> str:
        value = self._optional_env(name)
        if not value:
            raise LlmRoutingConfigurationError(
                f"{name} is required when {PREVIOUS_SESSION_SUMMARY_ROUTE_ENV}="
                f"{route.value}"
            )
        return value

    def _emit_safe_event(self, event: str, **fields: Any) -> None:
        payload = {
            "event": event,
            "workload": PREVIOUS_SESSION_SUMMARY_WORKLOAD,
            **fields,
        }
        try:
            self._event_logger.info(
                json.dumps(payload, separators=(",", ":"), sort_keys=True)
            )
        except Exception:
            # Telemetry delivery must never change a clinical call's result.
            pass


def _validate_gateway_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/v1"
    ):
        raise LlmRoutingConfigurationError(
            f"{GATEWAY_BASE_URL_ENV} must be an absolute gateway URL ending in /v1"
        )

    if parsed.scheme == "http" and parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise LlmRoutingConfigurationError(
            f"{GATEWAY_BASE_URL_ENV} must use HTTPS outside local development"
        )
    return value.rstrip("/")


def _validate_model_alias(value: str, env_name: str) -> str:
    if not MODEL_ALIAS_PATTERN.fullmatch(value):
        raise LlmRoutingConfigurationError(
            f"{env_name} must contain one stable model alias"
        )
    return value


def _elapsed_milliseconds(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))
