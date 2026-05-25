"""
Regression tests for the scribe Refine tab — 2026-05-25 outage.

Background. Sally-Anne reported that the web Refine tab silently ignored her
edit instructions (e.g. "change Hermione to Sally-Anne" still rendered the
document with Hermione). Root cause: `generate_document_from_context` only
detected refinement framings starting with `"CRITICAL INSTRUCTIONS FOR AI
ASSISTANT:"` (the marker Haystack's own `tools.py::_refine_document` emits).
The web Refine tab (web PR #277) sends a different framing — `ORIGINAL
DOCUMENT:` / `REQUESTED MODIFICATIONS:` markers. That framing fell through
to the "normal generation" branch, which wrapped the refine-prompt as if it
were a fresh template and re-ran agentic generation against the transcripts,
silently dropping the user's edit.

These tests pin the routing behaviour. Without the fix, the web-refinement
test fails (the user prompt contains transcript context instead of the
refine-only edit framing).
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from document_generation.generator import generate_document_from_context  # noqa: E402


def _make_openai_client(captured: List[Dict[str, Any]]) -> MagicMock:
    """A mock OpenAI client that captures the messages it was called with."""
    client = MagicMock()

    async def fake_create(**kwargs):
        captured.append(kwargs)
        response = MagicMock()
        choice = MagicMock()
        choice.message.content = "REFINED DOCUMENT CONTENT"
        choice.finish_reason = "stop"
        response.choices = [choice]
        response.usage = MagicMock(total_tokens=42)
        return response

    client.chat.completions.create = AsyncMock(side_effect=fake_create)
    return client


WEB_REFINEMENT_TEMPLATE = """You are refining an existing clinical document. Return the FULL refined document, preserving its original structure, section headings, and clinical tone. Apply ONLY the requested modifications — do NOT regenerate from scratch from the transcripts.

ORIGINAL DOCUMENT:
SOAP note. S: Hermione reported low mood... O: Hermione presented as... A: ... P: ...

REQUESTED MODIFICATIONS:
change Hermione to Sally-Anne

REFINED DOCUMENT:"""


def test_web_refinement_routes_to_edit_prompt():
    """
    Web Refine tab framing must route to the refinement prompt builder, NOT
    the normal generation branch. The user prompt sent to OpenAI MUST:
      - tell the model to apply ONLY the requested modifications
      - tell it NOT to regenerate from transcripts
      - contain the original document and the requested modification verbatim
      - NOT include the session transcript as a "Source Content" section
        (its presence tempts the model to regenerate from scratch)
    """
    captured: List[Dict[str, Any]] = []
    openai_client = _make_openai_client(captured)

    transcript_segments = [
        {
            "speaker": "Therapist",
            "text": "How have you been since our last session?",
            "start_time": 0,
            "transcript_id": "tx-1",
        },
        {
            "speaker": "Client",
            "text": "Not great, my mood has been low.",
            "start_time": 5,
            "transcript_id": "tx-1",
        },
    ]

    asyncio.run(generate_document_from_context(
        segments=transcript_segments,
        template={
            "id": "tmpl-1",
            "name": "SOAP note",
            "content": WEB_REFINEMENT_TEMPLATE,
        },
        client_info={"id": "c-1", "name": "Sally-Anne"},
        practitioner_info={"id": "p-1", "name": "Dr Smith"},
        generation_instructions=None,
        openai_client=openai_client,
    ))

    assert len(captured) == 1, "OpenAI should be called exactly once"
    messages = captured[0]["messages"]
    user_prompt = next(m["content"] for m in messages if m["role"] == "user")

    # The refine-framed markers must reach the model verbatim.
    assert "ORIGINAL DOCUMENT:" in user_prompt
    assert "REQUESTED MODIFICATIONS:" in user_prompt
    assert "change Hermione to Sally-Anne" in user_prompt

    # Edit framing must be explicit.
    assert "Apply ONLY the requested modifications" in user_prompt
    assert "Do NOT regenerate" in user_prompt or "do NOT regenerate" in user_prompt

    # Critically — the normal-generation user prompt opens with "Generate a
    # comprehensive clinical document." and embeds the transcript under a
    # "Source Content" / "Session Transcript" heading. Neither must appear:
    # if they do, we've fallen through to the regeneration-from-transcript
    # path and the user's edit will be ignored. This is the regression the
    # 2026-05-25 outage exposed.
    assert "Generate a comprehensive clinical document" not in user_prompt
    assert "Session Transcript" not in user_prompt
    assert "How have you been since our last session?" not in user_prompt


def test_legacy_regeneration_marker_still_routes_to_edit_prompt():
    """
    Haystack's own `_refine_document` tool emits a refinement prompt starting
    with "CRITICAL INSTRUCTIONS FOR AI ASSISTANT:". This existing path must
    continue to work — the fix is additive.
    """
    captured: List[Dict[str, Any]] = []
    openai_client = _make_openai_client(captured)

    legacy_template = """CRITICAL INSTRUCTIONS FOR AI ASSISTANT:
- NEVER provide diagnoses

Please refine the following document according to these instructions:

**Refinement Instructions:** use first names only

**Original Document:**
Dr Smith met with Sally-Anne Jones today.
"""

    asyncio.run(generate_document_from_context(
        segments=[],
        template={"id": "t", "name": "Refine", "content": legacy_template},
        client_info={"id": "c-1", "name": "Sally-Anne"},
        practitioner_info={"id": "p-1", "name": "Dr Smith"},
        generation_instructions=None,
        openai_client=openai_client,
    ))

    assert len(captured) == 1
    user_prompt = next(
        m["content"] for m in captured[0]["messages"] if m["role"] == "user"
    )
    assert "Modify the existing document based on the modification request" in user_prompt
    # Legacy path still embeds the original template verbatim.
    assert "use first names only" in user_prompt


def test_normal_template_still_routes_to_generation():
    """
    A plain template (no refinement markers) must still flow through the
    normal generation path, embedding the transcript as Source Content.
    """
    captured: List[Dict[str, Any]] = []
    openai_client = _make_openai_client(captured)

    asyncio.run(generate_document_from_context(
        segments=[
            {
                "speaker": "Therapist",
                "text": "How are you?",
                "start_time": 0,
                "transcript_id": "tx-1",
            }
        ],
        template={
            "id": "tmpl-1",
            "name": "SOAP",
            "content": "Generate a SOAP note covering Subjective, Objective, Assessment, Plan.",
        },
        client_info={"id": "c-1", "name": "Sally-Anne"},
        practitioner_info={"id": "p-1", "name": "Dr Smith"},
        generation_instructions=None,
        openai_client=openai_client,
    ))

    user_prompt = next(
        m["content"] for m in captured[0]["messages"] if m["role"] == "user"
    )
    assert "Generate a comprehensive clinical document" in user_prompt
    assert "Session Transcript" in user_prompt
    assert "How are you?" in user_prompt
