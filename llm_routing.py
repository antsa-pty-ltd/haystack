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

WEB_ASSISTANT_WORKLOAD = "web_assistant"
WEB_ASSISTANT_ROUTE_ENV = "HAYSTACK_LLM_ROUTE_WEB_ASSISTANT"
WEB_ASSISTANT_OPENAI_ALIAS_ENV = "HAYSTACK_LITELLM_MODEL_WEB_ASSISTANT_OPENAI"
WEB_ASSISTANT_FOUNDRY_ALIAS_ENV = "HAYSTACK_LITELLM_MODEL_WEB_ASSISTANT_FOUNDRY"

THERAPIST_WORKLOAD = "therapist"
THERAPIST_ROUTE_ENV = "HAYSTACK_LLM_ROUTE_THERAPIST"
THERAPIST_OPENAI_ALIAS_ENV = "HAYSTACK_LITELLM_MODEL_THERAPIST_OPENAI"
THERAPIST_FOUNDRY_ALIAS_ENV = "HAYSTACK_LITELLM_MODEL_THERAPIST_FOUNDRY"

COMPANION_WORKLOAD = "companion"
COMPANION_ROUTE_ENV = "HAYSTACK_LLM_ROUTE_COMPANION"
COMPANION_OPENAI_ALIAS_ENV = "HAYSTACK_LITELLM_MODEL_COMPANION_OPENAI"
COMPANION_FOUNDRY_ALIAS_ENV = "HAYSTACK_LITELLM_MODEL_COMPANION_FOUNDRY"

TRANSCRIBER_WORKLOAD = "transcriber"
TRANSCRIBER_ROUTE_ENV = "HAYSTACK_LLM_ROUTE_TRANSCRIBER"
TRANSCRIBER_OPENAI_ALIAS_ENV = "HAYSTACK_LITELLM_MODEL_TRANSCRIBER_OPENAI"
TRANSCRIBER_FOUNDRY_ALIAS_ENV = "HAYSTACK_LITELLM_MODEL_TRANSCRIBER_FOUNDRY"

DOCUMENT_AGENT_WORKLOAD = "document_agent"
DOCUMENT_AGENT_ROUTE_ENV = "HAYSTACK_LLM_ROUTE_DOCUMENT_AGENT"
DOCUMENT_AGENT_OPENAI_ALIAS_ENV = "HAYSTACK_LITELLM_MODEL_DOCUMENT_AGENT_OPENAI"
DOCUMENT_AGENT_FOUNDRY_ALIAS_ENV = "HAYSTACK_LITELLM_MODEL_DOCUMENT_AGENT_FOUNDRY"

DOCUMENT_DRAFT_WORKLOAD = "document_draft"
DOCUMENT_DRAFT_DIRECT_MODEL = "gpt-5.4-mini"
DOCUMENT_DRAFT_ROUTE_ENV = "HAYSTACK_LLM_ROUTE_DOCUMENT_DRAFT"
DOCUMENT_DRAFT_OPENAI_ALIAS_ENV = "HAYSTACK_LITELLM_MODEL_DOCUMENT_DRAFT_OPENAI"
DOCUMENT_DRAFT_FOUNDRY_ALIAS_ENV = "HAYSTACK_LITELLM_MODEL_DOCUMENT_DRAFT_FOUNDRY"

DOCUMENT_LANGUAGE_WORKLOAD = "document_language"
DOCUMENT_LANGUAGE_DIRECT_MODEL = "gpt-5.4-mini"
DOCUMENT_LANGUAGE_ROUTE_ENV = "HAYSTACK_LLM_ROUTE_DOCUMENT_LANGUAGE"
DOCUMENT_LANGUAGE_OPENAI_ALIAS_ENV = (
    "HAYSTACK_LITELLM_MODEL_DOCUMENT_LANGUAGE_OPENAI"
)
DOCUMENT_LANGUAGE_FOUNDRY_ALIAS_ENV = (
    "HAYSTACK_LITELLM_MODEL_DOCUMENT_LANGUAGE_FOUNDRY"
)

DOCUMENT_POLICY_WORKLOAD = "document_policy"
DOCUMENT_POLICY_DIRECT_MODEL = "gpt-4o-mini"
DOCUMENT_POLICY_ROUTE_ENV = "HAYSTACK_LLM_ROUTE_DOCUMENT_POLICY"
DOCUMENT_POLICY_OPENAI_ALIAS_ENV = "HAYSTACK_LITELLM_MODEL_DOCUMENT_POLICY_OPENAI"
DOCUMENT_POLICY_FOUNDRY_ALIAS_ENV = (
    "HAYSTACK_LITELLM_MODEL_DOCUMENT_POLICY_FOUNDRY"
)

CONVERSATION_SUMMARY_WORKLOAD = "conversation_summary"
CONVERSATION_SUMMARY_DIRECT_MODEL = "gpt-4o-mini"
CONVERSATION_SUMMARY_ROUTE_ENV = "HAYSTACK_LLM_ROUTE_CONVERSATION_SUMMARY"
CONVERSATION_SUMMARY_OPENAI_ALIAS_ENV = (
    "HAYSTACK_LITELLM_MODEL_CONVERSATION_SUMMARY_OPENAI"
)
CONVERSATION_SUMMARY_FOUNDRY_ALIAS_ENV = (
    "HAYSTACK_LITELLM_MODEL_CONVERSATION_SUMMARY_FOUNDRY"
)

CHAT_WORKLOAD = "chat"
CHAT_ROUTE_ENV = "HAYSTACK_LLM_ROUTE_CHAT"
CHAT_OPENAI_ALIAS_ENV = "HAYSTACK_LITELLM_MODEL_CHAT_OPENAI"
CHAT_FOUNDRY_ALIAS_ENV = "HAYSTACK_LITELLM_MODEL_CHAT_FOUNDRY"


class LlmRoute(str, Enum):
    DIRECT_OPENAI = "direct_openai"
    LITELLM_OPENAI = "litellm_openai"
    LITELLM_FOUNDRY = "litellm_foundry"


class LlmRoutingConfigurationError(ValueError):
    """Raised when a selected, server-controlled route is not configured."""


@dataclass(frozen=True)
class LlmTarget:
    """The resolved destination for one isolated LLM workload.

    For litellm routes, ``gateway_base_url`` and ``gateway_api_key`` carry the
    gateway connection details. These are secrets: they must never be logged
    or emitted in telemetry of any kind.
    """

    workload: str
    route: LlmRoute
    model: str
    client: Any
    gateway_base_url: Optional[str] = None
    gateway_api_key: Optional[str] = None


GatewayClientFactory = Callable[..., Any]
TargetOperation = Callable[[LlmTarget], Awaitable[Any]]


class LlmWorkloadRouter:
    """Resolve and observe one server-controlled LLM workload at startup."""

    def __init__(
        self,
        *,
        workload: str,
        route_env: str,
        openai_alias_env: str,
        foundry_alias_env: str,
        direct_model: Optional[str] = None,
        direct_client: Any = None,
        environ: Optional[Mapping[str, str]] = None,
        gateway_client_factory: GatewayClientFactory = AsyncOpenAI,
        event_logger: Optional[logging.Logger] = None,
    ) -> None:
        self._workload = workload
        self._route_env = route_env
        self._openai_alias_env = openai_alias_env
        self._foundry_alias_env = foundry_alias_env
        self._direct_model = direct_model or ""
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
        route_value = self._optional_env(self._route_env) or (
            LlmRoute.DIRECT_OPENAI.value
        )
        try:
            route = LlmRoute(route_value)
        except ValueError as error:
            allowed_routes = ", ".join(route.value for route in LlmRoute)
            raise LlmRoutingConfigurationError(
                f"{self._route_env} must be one of: "
                f"{allowed_routes}"
            ) from error

        if route is LlmRoute.DIRECT_OPENAI:
            return LlmTarget(
                workload=self._workload,
                route=route,
                model=self._direct_model,
                client=direct_client,
            )

        base_url = _validate_gateway_base_url(
            self._required_env(GATEWAY_BASE_URL_ENV, route)
        )
        gateway_api_key = self._required_env(
            HAYSTACK_GATEWAY_API_KEY_ENV, route
        )
        alias_env = (
            self._openai_alias_env
            if route is LlmRoute.LITELLM_OPENAI
            else self._foundry_alias_env
        )
        model_alias = _validate_model_alias(
            self._required_env(alias_env, route), alias_env
        )
        gateway_client = gateway_client_factory(
            api_key=gateway_api_key,
            base_url=base_url,
        )
        return LlmTarget(
            workload=self._workload,
            route=route,
            model=model_alias,
            client=gateway_client,
            gateway_base_url=base_url,
            gateway_api_key=gateway_api_key,
        )

    def _optional_env(self, name: str) -> str:
        return (self._environ.get(name) or "").strip()

    def _required_env(self, name: str, route: LlmRoute) -> str:
        value = self._optional_env(name)
        if not value:
            raise LlmRoutingConfigurationError(
                f"{name} is required when {self._route_env}="
                f"{route.value}"
            )
        return value

    def _emit_safe_event(self, event: str, **fields: Any) -> None:
        payload = {
            "event": event,
            "workload": self._workload,
            **fields,
        }
        if not payload.get("model"):
            payload.pop("model", None)
        try:
            self._event_logger.info(
                json.dumps(payload, separators=(",", ":"), sort_keys=True)
            )
        except Exception:
            # Telemetry delivery must never change a clinical call's result.
            pass


class PreviousSessionSummaryRouter(LlmWorkloadRouter):
    """Resolve and observe only the durable previous-session summary call."""

    def __init__(
        self,
        direct_client: Any,
        *,
        environ: Optional[Mapping[str, str]] = None,
        gateway_client_factory: GatewayClientFactory = AsyncOpenAI,
        event_logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(
            workload=PREVIOUS_SESSION_SUMMARY_WORKLOAD,
            route_env=PREVIOUS_SESSION_SUMMARY_ROUTE_ENV,
            openai_alias_env=PREVIOUS_SESSION_SUMMARY_OPENAI_ALIAS_ENV,
            foundry_alias_env=PREVIOUS_SESSION_SUMMARY_FOUNDRY_ALIAS_ENV,
            direct_model=PREVIOUS_SESSION_SUMMARY_DIRECT_MODEL,
            direct_client=direct_client,
            environ=environ,
            gateway_client_factory=gateway_client_factory,
            event_logger=event_logger,
        )


class LlmRouterRegistry:
    """Hold the startup-resolved routers call-sites fetch by workload id.

    Registering the same workload twice replaces the previous router
    silently; this keeps startup re-resolution simple and deterministic.
    """

    def __init__(self) -> None:
        self._routers: dict[str, LlmWorkloadRouter] = {}

    def register(self, router: LlmWorkloadRouter) -> None:
        self._routers[router.target.workload] = router

    def get(self, workload: str) -> LlmWorkloadRouter:
        try:
            return self._routers[workload]
        except KeyError:
            raise RuntimeError(
                f"No LLM router registered for workload: {workload}"
            ) from None

    def clear(self) -> None:
        """Drop every registered router (test isolation only)."""
        self._routers.clear()


router_registry = LlmRouterRegistry()


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
