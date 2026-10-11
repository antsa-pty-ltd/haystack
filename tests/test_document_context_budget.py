from unittest.mock import MagicMock

from openai import AsyncOpenAI

from agents.exploration_tools import ExplorationContext, _evenly_sample_segments
from document_generation.generator import (
    DOCUMENT_NOTES_MAX_CHARS,
    DOCUMENT_DRAFT_REQUEST_TIMEOUT_SECONDS,
    _bounded_draft_client,
    _bounded_notes_text,
)


def _segments(count: int):
    return [
        {
            "transcript_id": f"session-{index // 170}",
            "start_time": index,
            "speaker": "Practitioner",
            "text": f"Synthetic transcript segment {index} " + ("x" * 380),
        }
        for index in range(count)
    ]


def test_large_multi_session_context_stays_below_document_draft_budget():
    """ADO #419: 1,313 segments estimated to 98,475 tokens in production."""
    context = ExplorationContext()

    context.add_segments(_segments(1_313))

    assert context.tokens_used <= 45_000
    assert len(context.accumulated_segments) < 1_313


def test_document_draft_disables_sdk_retries_inside_azure_request_window():
    client = MagicMock(spec=AsyncOpenAI)
    bounded = object()
    client.with_options.return_value = bounded

    assert _bounded_draft_client(client) is bounded
    client.with_options.assert_called_once_with(
        max_retries=0,
        timeout=DOCUMENT_DRAFT_REQUEST_TIMEOUT_SECONDS,
    )


def test_large_sessions_are_sampled_across_the_full_timeline():
    segments = _segments(1_000)

    sampled = _evenly_sample_segments(segments, 4)

    assert [segment["start_time"] for segment in sampled] == [0, 333, 666, 999]


def test_multi_session_budget_reserves_tokens_for_four_representative_sessions():
    context = ExplorationContext(target_session_count=8)

    assert context.full_session_token_limit() == 11_250


def test_large_practitioner_notes_are_bounded_without_dropping_a_note():
    notes = [
        {
            "title": f"Synthetic note {index}",
            "content": f"START-{index} " + ("x" * 30_000) + f" END-{index}",
            "createdAt": "2026-10-11T00:00:00Z",
        }
        for index in range(3)
    ]

    rendered = _bounded_notes_text(notes)

    assert len(rendered) <= DOCUMENT_NOTES_MAX_CHARS
    for index in range(3):
        assert f"START-{index}" in rendered
        assert f"END-{index}" in rendered
