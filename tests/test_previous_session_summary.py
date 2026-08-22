"""Contract tests for structured previous-session summaries."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from previous_session_summary import (
    PreviousSessionSummaryRequest,
    generate_previous_session_summary,
)


def _response(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def test_generates_all_required_sections_as_structured_data():
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=AsyncMock(
                    return_value=_response(
                        """{
                          "summary": "The client practised paced breathing.",
                          "keyTopics": ["anxiety", "sleep"],
                          "homeworkStatus": "Paced breathing was attempted twice.",
                          "insights": ["Evening practice was easier."],
                          "actionItems": ["Practise before bed."],
                          "moodTrend": "improving"
                        }"""
                    )
                )
            )
        )
    )

    result = asyncio.run(
        generate_previous_session_summary(
            PreviousSessionSummaryRequest(
                sessionId="session-1",
                transcript="Practitioner: How did the breathing practice go?",
                recordingDate="2026-08-20T10:00:00Z",
            ),
            client,
        )
    )

    assert result.summary == "The client practised paced breathing."
    assert result.keyTopics == ["anxiety", "sleep"]
    assert result.homeworkStatus == "Paced breathing was attempted twice."
    assert result.insights == ["Evening practice was easier."]
    assert result.actionItems == ["Practise before bed."]
    assert result.moodTrend == "improving"
    call = client.chat.completions.create.await_args.kwargs
    assert call["response_format"]["type"] == "json_schema"
    assert "Do not diagnose" in call["messages"][0]["content"]


def test_rejects_invalid_model_output_instead_of_persisting_partial_clinical_data():
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=AsyncMock(return_value=_response('{"summary": "Incomplete"}'))
            )
        )
    )

    with pytest.raises(ValueError, match="invalid structured summary"):
        asyncio.run(
            generate_previous_session_summary(
                PreviousSessionSummaryRequest(
                    sessionId="session-1",
                    transcript="A sufficiently long transcript for summary generation.",
                ),
                client,
            )
        )


def test_rejects_blank_transcript_without_calling_the_model():
    create = AsyncMock()
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )

    with pytest.raises(ValueError, match="transcript is empty"):
        asyncio.run(
            generate_previous_session_summary(
                PreviousSessionSummaryRequest(sessionId="session-1", transcript="   "),
                client,
            )
        )

    create.assert_not_awaited()
