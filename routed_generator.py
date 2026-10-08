"""Haystack generator adapter with payload-free per-call route telemetry."""

from typing import Any, Awaitable, Callable, Optional, Union

from haystack.components.generators.chat import OpenAIChatGenerator
from haystack import component
from haystack.dataclasses import ChatMessage, StreamingChunk
from haystack.tools import Tool, Toolset

from llm_routing import LlmWorkloadRouter


class RoutedOpenAIChatGenerator(OpenAIChatGenerator):
    """Observe a complete Haystack generator call through its selected router."""

    def __init__(self, *, llm_router: LlmWorkloadRouter, **kwargs: Any) -> None:
        self._llm_router = llm_router
        super().__init__(**kwargs)

    @component.output_types(replies=list[ChatMessage])
    def run(
        self,
        messages: list[ChatMessage],
        streaming_callback: Union[
            Callable[[StreamingChunk], None],
            Callable[[StreamingChunk], Awaitable[None]],
            None,
        ] = None,
        generation_kwargs: Optional[dict[str, Any]] = None,
        *,
        tools: Union[list[Tool], Toolset, None] = None,
        tools_strict: Optional[bool] = None,
    ):
        def generate(_target):
            return super(RoutedOpenAIChatGenerator, self).run(
                messages=messages,
                streaming_callback=streaming_callback,
                generation_kwargs=generation_kwargs,
                tools=tools,
                tools_strict=tools_strict,
            )

        return self._llm_router.execute_sync(generate)

    @component.output_types(replies=list[ChatMessage])
    async def run_async(
        self,
        messages: list[ChatMessage],
        streaming_callback: Union[
            Callable[[StreamingChunk], None],
            Callable[[StreamingChunk], Awaitable[None]],
            None,
        ] = None,
        generation_kwargs: Optional[dict[str, Any]] = None,
        *,
        tools: Union[list[Tool], Toolset, None] = None,
        tools_strict: Optional[bool] = None,
    ):
        async def generate(_target):
            return await super(RoutedOpenAIChatGenerator, self).run_async(
                messages=messages,
                streaming_callback=streaming_callback,
                generation_kwargs=generation_kwargs,
                tools=tools,
                tools_strict=tools_strict,
            )

        return await self._llm_router.execute(generate)
