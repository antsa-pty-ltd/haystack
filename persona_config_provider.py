"""Load the current administrator-published persona configuration.

The Nest API owns immutable versions. Haystack asks for the current version on
every chat turn so a publish takes effect without an app restart. A successful
configuration is retained as the last-known-good value; API/network failures
therefore never replace a working production persona with an empty or partial
configuration.
"""

import asyncio
import logging
import os
from typing import Dict

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

from config import settings
from personas import PersonaConfig, PersonaType, normalize_persona_type, persona_manager

logger = logging.getLogger(__name__)


class PublishedPersonaConfig(BaseModel):
    version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    system_prompt: str = Field(alias="systemPrompt", min_length=20, max_length=100000)
    model: str = Field(min_length=1, max_length=120)
    temperature: float = Field(ge=0, le=2)
    max_completion_tokens: int = Field(alias="maxCompletionTokens", ge=1, le=32768)
    has_db_access: bool = Field(alias="hasDbAccess")
    tool_names: list[str] = Field(alias="toolNames", max_length=100)

    @field_validator("tool_names")
    @classmethod
    def tool_names_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("toolNames must be unique")
        return value


class PersonaConfigProvider:
    def __init__(self) -> None:
        self._last_known_good: Dict[PersonaType, PersonaConfig] = {}
        self._locks: Dict[PersonaType, asyncio.Lock] = {}

    async def get(self, persona_type: PersonaType) -> PersonaConfig:
        canonical = self._canonical(persona_type)
        if canonical not in (
            PersonaType.WEB_ASSISTANT,
            PersonaType.ANTSABOT_THERAPIST,
            PersonaType.ANTSABOT_COMPANION,
        ):
            return persona_manager.get_persona(canonical)

        lock = self._locks.setdefault(canonical, asyncio.Lock())
        async with lock:
            try:
                published = await self._fetch(canonical)
                config = self._build_config(canonical, published)
                self._last_known_good[canonical] = config
                return config
            except (httpx.HTTPError, ValidationError, ValueError, KeyError) as error:
                cached = self._last_known_good.get(canonical)
                if cached:
                    logger.warning(
                        "persona-config: using last-known-good %s v%s after refresh failed: %s",
                        canonical.value,
                        cached.version,
                        error,
                    )
                    return cached
                logger.warning(
                    "persona-config: using built-in %s defaults after refresh failed: %s",
                    canonical.value,
                    error,
                )
                return persona_manager.get_persona(canonical)

    async def _fetch(self, persona_type: PersonaType) -> PublishedPersonaConfig:
        secret = os.getenv("HAYSTACK_WEBHOOK_SECRET")
        if not secret:
            raise ValueError("HAYSTACK_WEBHOOK_SECRET is not configured")
        base_url = settings.nestjs_api_url.rstrip("/")
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(
                f"{base_url}/api/v1/ai/persona-configs/{persona_type.value}",
                headers={"X-Haystack-Secret": secret},
            )
            response.raise_for_status()
            return PublishedPersonaConfig.model_validate(response.json())

    def _build_config(
        self,
        persona_type: PersonaType,
        published: PublishedPersonaConfig,
    ) -> PersonaConfig:
        built_in = persona_manager.get_persona(persona_type)
        available_names = {
            tool.get("function", {}).get("name")
            for tool in built_in.tools
            if isinstance(tool, dict)
        }
        unknown = [name for name in published.tool_names if name not in available_names]
        if unknown:
            raise ValueError(
                f"published {persona_type.value} config contains unavailable tools: {', '.join(unknown)}"
            )
        selected = set(published.tool_names)
        return PersonaConfig(
            version=published.version,
            name=published.name,
            description=published.description,
            system_prompt=published.system_prompt,
            model=published.model,
            temperature=published.temperature,
            max_completion_tokens=published.max_completion_tokens,
            has_db_access=published.has_db_access,
            tools=[
                tool
                for tool in built_in.tools
                if tool.get("function", {}).get("name") in selected
            ],
            available_functions={
                name: function
                for name, function in built_in.available_functions.items()
                if name in selected
            },
        )

    @staticmethod
    def _canonical(persona_type: PersonaType) -> PersonaType:
        return PersonaType(normalize_persona_type(persona_type.value))


persona_config_provider = PersonaConfigProvider()
