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


def test_first_name_template_explains_name_part_tokens_without_full_name_override():
    captured = []
    asyncio.run(generate_document_from_context(
        segments=[],
        template={"id": "t", "name": "Note", "content": "Use the client's first name only. Keep this concise."},
        client_info={"name": "[CLIENT_NAME]", "firstName": "[CLIENT_FIRST_NAME]", "lastName": "[CLIENT_LAST_NAME]"},
        practitioner_info={"name": "[PRACTITIONER_NAME]"},
        generation_instructions=None, openai_client=_make_openai_client(captured),
    ))
    prompt = '\n'.join(m['content'] for m in captured[0]['messages'])
    assert '[CLIENT_FIRST_NAME]' in prompt
    assert 'never use [CLIENT_NAME] or [CLIENT_LAST_NAME] in that case' in prompt
    assert '800-1500' not in prompt
    assert 'Do NOT replace these tokens with generic terms' not in prompt


@pytest.mark.parametrize('instructions,maximum', [
    ('Shorten by 50%', 150), ('Reduce to 50 percent', 150),
    ('Make it more concise', 225), ('Cut it in half', 150),
    ('Shorten to 100 words', 100),
])
def test_shortening_retries_expanded_output_and_measures_against_original(instructions, maximum):
    captured = []
    client = _make_openai_client(captured)
    expanded = MagicMock()
    expanded.choices = [MagicMock(message=MagicMock(content='word ' * 412), finish_reason='stop')]
    shortened = MagicMock()
    shortened.choices = [MagicMock(message=MagicMock(content='word ' * maximum), finish_reason='stop')]
    client.chat.completions.create = AsyncMock(side_effect=[expanded, shortened])
    original = 'word ' * 301
    result = asyncio.run(generate_document_from_context(
        segments=[], template={'id': 't', 'name': 'Note', 'content': f'ORIGINAL DOCUMENT:\n{original}\nREQUESTED MODIFICATIONS:\n{instructions}\nREFINED DOCUMENT:'},
        client_info={'name': '[CLIENT_NAME]'}, practitioner_info={'name': '[PRACTITIONER_NAME]'},
        generation_instructions=None, openai_client=client,
    ))
    assert result['metadata']['wordCount'] <= maximum
    assert client.chat.completions.create.await_count == 2
    retry = client.chat.completions.create.call_args.kwargs['messages'][-1]['content']
    assert f'maximum of {maximum}' in retry


def test_shortening_does_not_return_or_truncate_an_oversized_result():
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content='word ' * 412), finish_reason='stop')]
    client.chat.completions.create = AsyncMock(return_value=response)
    with pytest.raises(ValueError, match='could not be shortened'):
        asyncio.run(generate_document_from_context(
            segments=[], template={'content': f"ORIGINAL DOCUMENT:\n{'word ' * 301}\nREQUESTED MODIFICATIONS:\nShorten by 50%\nREFINED DOCUMENT:"},
            client_info={'name': '[CLIENT_NAME]'}, practitioner_info={'name': '[PRACTITIONER_NAME]'},
            generation_instructions=None, openai_client=client,
        ))
    assert client.chat.completions.create.await_count == 3


def test_legacy_refinement_omits_source_and_comprehensive_detail_requirement():
    captured = []
    asyncio.run(generate_document_from_context(
        segments=[{'text': 'UNRELATED TRANSCRIPT CONTENT'}],
        template={'content': 'CRITICAL INSTRUCTIONS FOR AI ASSISTANT:\n\n**Refinement Instructions:** remove the client surname\n**Original Document:**\n[CLIENT_NAME] attended.\n**Instructions for refinement:**\nKeep professional.'},
        client_info={'name': '[CLIENT_NAME]'}, practitioner_info={'name': '[PRACTITIONER_NAME]'},
        generation_instructions='Reference document: unrelated background',
        openai_client=_make_openai_client(captured),
    ))
    prompt = '\n'.join(m['content'] for m in captured[0]['messages'])
    assert 'Keep comprehensive detail' not in prompt
    assert 'UNRELATED TRANSCRIPT CONTENT' not in prompt
    assert 'Regenerate the document incorporating' not in prompt


def test_refinement_endpoint_skips_transcript_exploration():
    from types import SimpleNamespace
    from unittest.mock import patch
    from document_generation.agentic_endpoint import generate_document_from_template_agentic
    request = SimpleNamespace(
        generationId='synthetic-generation', template={'content': WEB_REFINEMENT_TEMPLATE},
        sessionIds=['old-session'], sessionData=[], dictatedNotes=[],
        clientInfo={'name': '[CLIENT_NAME]'}, practitionerInfo={'name': '[PRACTITIONER_NAME]'},
        generationInstructions=None,
    )
    with patch('document_generation.agentic_endpoint.get_document_agent') as agent:
        result = asyncio.run(generate_document_from_template_agentic(
            request, MagicMock(), 'Bearer synthetic', 'synthetic-profile',
            _make_openai_client([]), AsyncMock(),
            AsyncMock(return_value={'is_violation': False}), AsyncMock(),
        ))
    agent.assert_not_called()
    assert result['content'] == 'REFINED DOCUMENT CONTENT'
    assert result['metadata']['processingMethod'] == 'document_refinement'


def test_failed_shortening_is_an_http_error_not_a_saveable_document():
    from types import SimpleNamespace
    from unittest.mock import patch
    from fastapi import HTTPException
    from document_generation.agentic_endpoint import generate_document_from_template_agentic
    from document_generation.refinement import RefinementValidationError
    request = SimpleNamespace(
        generationId='synthetic-generation', template={'content': WEB_REFINEMENT_TEMPLATE},
        sessionIds=[], sessionData=[], dictatedNotes=[],
        clientInfo={'name': '[CLIENT_NAME]'}, practitionerInfo={'name': '[PRACTITIONER_NAME]'},
        generationInstructions=None,
    )
    with patch('document_generation.agentic_endpoint.generate_document_from_context',
               new=AsyncMock(side_effect=RefinementValidationError('The document could not be shortened.'))):
        with pytest.raises(HTTPException) as error:
            asyncio.run(generate_document_from_template_agentic(
                request, MagicMock(), 'Bearer synthetic', 'synthetic-profile',
                _make_openai_client([]), AsyncMock(),
                AsyncMock(return_value={'is_violation': False}), AsyncMock(),
            ))
    assert error.value.status_code == 422
    assert 'could not be shortened' in error.value.detail


@pytest.mark.parametrize('instructions', [
    "Do not shorten the document", "Mention that the goal is to reduce anxiety by 50%",
    "Add that the client took shorter walks", "Replace the surname with a first name",
])
def test_non_shortening_edits_do_not_impose_a_word_limit(instructions):
    from document_generation.refinement import shortening_word_limit
    assert shortening_word_limit('word ' * 301, instructions) is None
