"""Bounded, full-coverage preparation for large document sources.

The document draft model must not receive an unbounded transcript, but silently
sampling a long treatment history can omit the one session that matters.  This
module maps every supplied transcript segment into bounded sections, summarises
those sections, and reduces the summaries until the final draft context is
safe.  Source content remains tokenised throughout this service.
"""

from __future__ import annotations

import asyncio
import math
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional

from document_generation.generator import (
    _bounded_draft_client,
    _create_with_outcome,
    _draft_provider,
)
from llm_routing import gateway_chat_compatibility


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        configured = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        configured = default
    return max(minimum, min(configured, maximum))


def source_chunk_token_budget() -> int:
    return _bounded_int("DOCUMENT_SOURCE_CHUNK_TOKEN_BUDGET", 12_000, 4_000, 24_000)


def reduced_context_token_budget() -> int:
    return _bounded_int("DOCUMENT_REDUCED_CONTEXT_TOKEN_BUDGET", 32_000, 8_000, 42_000)


def summary_max_completion_tokens() -> int:
    return _bounded_int("DOCUMENT_SECTION_SUMMARY_MAX_TOKENS", 1_000, 300, 2_000)


def estimate_text_tokens(value: str) -> int:
    """Conservative token estimate without adding a tokenizer dependency."""
    return max(1, math.ceil((len(value.encode("utf-8")) + 32) / 4))


def _session_id(session: Dict[str, Any], index: int) -> str:
    return str(session.get("sessionId") or session.get("id") or f"session-{index + 1}")


def _session_date(session: Dict[str, Any]) -> str:
    value = session.get("recordingDate") or session.get("createdAt") or "date unavailable"
    return str(value).split("T", 1)[0]


def normalise_session_segments(session_data: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return every supplied segment with stable session and chronology labels."""
    sessions = list(session_data)
    total_sessions = len(sessions)
    normalised: List[Dict[str, Any]] = []
    for session_index, session in enumerate(sessions):
        session_id = _session_id(session, session_index)
        purpose = f"Session {session_index + 1} of {total_sessions} — {_session_date(session)}"
        for segment_index, segment in enumerate(session.get("segments") or []):
            normalised.append(
                {
                    **segment,
                    "transcript_id": session_id,
                    "start_time": segment.get("start_time", segment.get("startTime", segment_index)),
                    "speaker": segment.get("speaker") or "Speaker",
                    "text": str(segment.get("text") or ""),
                    "_search_purpose": purpose,
                    "_source_session_index": session_index,
                    "_source_segment_index": segment_index,
                }
            )
    return normalised


def estimate_session_data_tokens(session_data: Iterable[Dict[str, Any]]) -> int:
    return sum(
        estimate_text_tokens(f'{segment.get("speaker", "Speaker")}: {segment.get("text", "")}')
        for segment in normalise_session_segments(session_data)
    )


@dataclass(frozen=True)
class SourceChunk:
    session_id: str
    session_number: int
    session_count: int
    session_date: str
    part_number: int
    segments: List[Dict[str, Any]]
    estimated_tokens: int

    @property
    def label(self) -> str:
        return (
            f"Session {self.session_number} of {self.session_count} "
            f"({_safe_label(self.session_date)}), section {self.part_number}"
        )


def _safe_label(value: str) -> str:
    return value.replace("\n", " ").replace("\r", " ")


def _split_oversized_segment(segment: Dict[str, Any], token_budget: int) -> List[Dict[str, Any]]:
    text = str(segment.get("text") or "")
    if estimate_text_tokens(f'{segment.get("speaker", "Speaker")}: {text}') <= token_budget:
        return [segment]
    speaker = str(segment.get("speaker") or "Speaker")[:256]
    # The estimator is UTF-8 byte based. Split on character boundaries while
    # enforcing that same byte budget so emoji/non-Latin transcripts cannot
    # create an oversized model request.
    fixed_bytes = len(f"{speaker}: ".encode("utf-8")) + 32
    text_byte_budget = max(1, (token_budget * 4) - fixed_bytes)
    parts: List[str] = []
    start = 0
    used_bytes = 0
    for index, character in enumerate(text):
        character_bytes = len(character.encode("utf-8"))
        if index > start and used_bytes + character_bytes > text_byte_budget:
            parts.append(text[start:index])
            start = index
            used_bytes = 0
        used_bytes += character_bytes
    if start < len(text):
        parts.append(text[start:])
    return [
        {**segment, "speaker": speaker, "text": part, "_source_text_part": index + 1}
        for index, part in enumerate(parts)
    ]


def chunk_session_data(
    session_data: Iterable[Dict[str, Any]], token_budget: Optional[int] = None
) -> List[SourceChunk]:
    """Partition every source segment without crossing session boundaries."""
    budget = token_budget or source_chunk_token_budget()
    sessions = list(session_data)
    chunks: List[SourceChunk] = []
    for session_index, session in enumerate(sessions):
        session_id = _session_id(session, session_index)
        session_date = _session_date(session)
        source_segments: List[Dict[str, Any]] = []
        for segment_index, segment in enumerate(session.get("segments") or []):
            normalised = {
                **segment,
                "transcript_id": session_id,
                "start_time": segment.get("start_time", segment.get("startTime", segment_index)),
                "speaker": segment.get("speaker") or "Speaker",
                "text": str(segment.get("text") or ""),
                "_source_session_index": session_index,
                "_source_segment_index": segment_index,
            }
            source_segments.extend(_split_oversized_segment(normalised, budget))

        current: List[Dict[str, Any]] = []
        current_tokens = 0
        part_number = 1
        for segment in source_segments:
            segment_tokens = estimate_text_tokens(f'{segment["speaker"]}: {segment["text"]}')
            if current and current_tokens + segment_tokens > budget:
                chunks.append(
                    SourceChunk(
                        session_id=session_id,
                        session_number=session_index + 1,
                        session_count=len(sessions),
                        session_date=session_date,
                        part_number=part_number,
                        segments=current,
                        estimated_tokens=current_tokens,
                    )
                )
                current = []
                current_tokens = 0
                part_number += 1
            current.append(segment)
            current_tokens += segment_tokens
        if current:
            chunks.append(
                SourceChunk(
                    session_id=session_id,
                    session_number=session_index + 1,
                    session_count=len(sessions),
                    session_date=session_date,
                    part_number=part_number,
                    segments=current,
                    estimated_tokens=current_tokens,
                )
            )
    return chunks


def _render_segments(segments: Iterable[Dict[str, Any]]) -> str:
    lines = []
    for segment in segments:
        start = segment.get("start_time", segment.get("startTime", 0))
        lines.append(f'[{start}] {segment.get("speaker", "Speaker")}: {segment.get("text", "")}')
    return "\n".join(lines)


def _status_code(error: Exception) -> Optional[int]:
    value = getattr(error, "status_code", None)
    if isinstance(value, int):
        return value
    response = getattr(error, "response", None)
    response_status = getattr(response, "status_code", None)
    return response_status if isinstance(response_status, int) else None


def _retry_after_seconds(error: Exception, attempt: int) -> float:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", {}) or {}
    raw_milliseconds = headers.get("retry-after-ms")
    if raw_milliseconds is not None:
        try:
            return max(1.0, min(float(raw_milliseconds) / 1_000, 60.0))
        except ValueError:
            pass
    raw_reset = headers.get("x-ratelimit-reset-tokens")
    if raw_reset is not None:
        try:
            value = float(str(raw_reset).rstrip("s"))
            return max(1.0, min(value, 60.0))
        except ValueError:
            pass
    raw_seconds = headers.get("retry-after")
    if raw_seconds is not None:
        try:
            return max(1.0, min(float(raw_seconds), 60.0))
        except ValueError:
            pass
    return float(min(10 * (attempt + 1), 30))


async def _summarise_text(
    *,
    source_label: str,
    source_text: str,
    template_name: str,
    template_content: str,
    openai_client,
    emit_progress: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> str:
    draft_client, draft_model, draft_router = _draft_provider(openai_client)
    draft_client = _bounded_draft_client(draft_client)
    compatibility = gateway_chat_compatibility(draft_router.target) if draft_router else {}
    messages = [
        {
            "role": "system",
            "content": (
                "Summarise tokenised clinical source material for a later document-writing step. "
                "Preserve chronology, explicit presenting concerns, interventions, client responses, "
                "risk or safety statements, homework, plans, outcomes, and material changes. Do not "
                "diagnose, infer facts, or replace privacy tokens. Keep concrete source evidence and "
                "return only concise structured bullets."
            ),
        },
        {
            "role": "user",
            "content": (
                f"SOURCE: {source_label}\n"
                f"DOCUMENT PURPOSE: {template_name}\n"
                f"TEMPLATE GUIDANCE:\n{template_content[:4_000]}\n\n"
                f"SOURCE MATERIAL:\n{source_text}"
            ),
        },
    ]

    for attempt in range(3):
        try:
            response = await _create_with_outcome(
                draft_router,
                lambda: draft_client.chat.completions.create(
                    model=draft_model,
                    messages=messages,
                    temperature=0.1,
                    max_completion_tokens=summary_max_completion_tokens(),
                    **compatibility,
                ),
            )
            content = response.choices[0].message.content if response and response.choices else None
            if not content or not content.strip():
                raise ValueError("Section summary returned no content")
            return content.strip()
        except Exception as error:
            if _status_code(error) != 429 or attempt == 2:
                raise
            delay = _retry_after_seconds(error, attempt)
            if emit_progress:
                await emit_progress(
                    {
                        "type": "progress_update",
                        "stage": "waiting_for_capacity",
                        "message": "AI capacity is busy. Your report is safe and will continue automatically...",
                        "details": {"retryInSeconds": round(delay), "retryable": True},
                    }
                )
            await sleep(delay)
    raise RuntimeError("unreachable")


@dataclass(frozen=True)
class LargeContextResult:
    segments: List[Dict[str, Any]]
    source_sessions: int
    source_segments: int
    source_sections: int
    reduction_levels: int


async def prepare_large_document_context(
    *,
    session_data: Iterable[Dict[str, Any]],
    template: Dict[str, Any],
    openai_client,
    emit_progress: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> LargeContextResult:
    """Process every source section and hierarchically reduce it for drafting."""
    sessions = list(session_data)
    chunks = chunk_session_data(sessions)
    source_segment_count = sum(len(session.get("segments") or []) for session in sessions)
    if not chunks:
        return LargeContextResult([], len(sessions), 0, 0, 0)

    summaries: List[Dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        if emit_progress:
            await emit_progress(
                {
                    "type": "progress_update",
                    "stage": "analysing_sessions",
                    "message": (
                        f"Analysing session {chunk.session_number} of {chunk.session_count} "
                        f"(section {index + 1} of {len(chunks)})..."
                    ),
                    "progress": {"current": index, "total": len(chunks)},
                    "details": {
                        "sessionCurrent": chunk.session_number,
                        "sessionTotal": chunk.session_count,
                        "sectionCurrent": index + 1,
                        "sectionTotal": len(chunks),
                        "allSourcesProcessed": False,
                    },
                }
            )
        summary = await _summarise_text(
            source_label=chunk.label,
            source_text=_render_segments(chunk.segments),
            template_name=str(template.get("name") or "Clinical document"),
            template_content=str(template.get("content") or ""),
            openai_client=openai_client,
            emit_progress=emit_progress,
            sleep=sleep,
        )
        summaries.append(
            {
                "transcript_id": chunk.session_id,
                "start_time": chunk.part_number,
                "speaker": "Source summary",
                "text": f"[{chunk.label}]\n{summary}",
                "_search_purpose": "Full-history section summaries",
            }
        )
        if emit_progress:
            await emit_progress(
                {
                    "type": "progress_update",
                    "stage": "analysing_sessions",
                    "message": f"Processed {index + 1} of {len(chunks)} report sections",
                    "progress": {"current": index + 1, "total": len(chunks)},
                    "details": {
                        "sessionCurrent": chunk.session_number,
                        "sessionTotal": chunk.session_count,
                        "sectionCurrent": index + 1,
                        "sectionTotal": len(chunks),
                        "allSourcesProcessed": index + 1 == len(chunks),
                    },
                }
            )

    reduction_levels = 0
    final_budget = reduced_context_token_budget()
    while sum(estimate_text_tokens(item["text"]) for item in summaries) > final_budget:
        reduction_levels += 1
        grouped: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = []
        current_tokens = 0
        for item in summaries:
            item_tokens = estimate_text_tokens(item["text"])
            if current and current_tokens + item_tokens > source_chunk_token_budget():
                grouped.append(current)
                current = []
                current_tokens = 0
            current.append(item)
            current_tokens += item_tokens
        if current:
            grouped.append(current)
        if len(grouped) >= len(summaries):
            # Summaries are already individually larger than the grouping
            # budget. The next summarisation call still reduces each item.
            grouped = [[item] for item in summaries]

        reduced: List[Dict[str, Any]] = []
        for index, group in enumerate(grouped):
            if emit_progress:
                await emit_progress(
                    {
                        "type": "progress_update",
                        "stage": "consolidating_context",
                        "message": f"Consolidating report evidence {index + 1} of {len(grouped)}...",
                        "progress": {"current": index, "total": len(grouped)},
                        "details": {"reductionLevel": reduction_levels},
                    }
                )
            text = "\n\n".join(item["text"] for item in group)
            reduced_text = await _summarise_text(
                source_label=f"Consolidated evidence group {index + 1} of {len(grouped)}",
                source_text=text,
                template_name=str(template.get("name") or "Clinical document"),
                template_content=str(template.get("content") or ""),
                openai_client=openai_client,
                emit_progress=emit_progress,
                sleep=sleep,
            )
            reduced.append(
                {
                    "transcript_id": f"reduction-{reduction_levels}-{index + 1}",
                    "start_time": index,
                    "speaker": "Consolidated source summary",
                    "text": reduced_text,
                    "_search_purpose": "Full-history consolidated evidence",
                }
            )
        summaries = reduced

    return LargeContextResult(
        segments=summaries,
        source_sessions=len(sessions),
        source_segments=source_segment_count,
        source_sections=len(chunks),
        reduction_levels=reduction_levels,
    )
