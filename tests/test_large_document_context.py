import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from document_generation.agentic_endpoint import generate_document_from_template_agentic
from document_generation.large_context import (
    LargeContextResult,
    _retry_after_seconds,
    _summarise_text,
    chunk_session_data,
    estimate_session_data_tokens,
    prepare_large_document_context,
)


def _sessions(session_count=8, segment_count=1_313):
    sessions = [
        {
            "sessionId": f"session-{index + 1}",
            "recordingDate": f"2026-0{min(index + 1, 9)}-01T00:00:00Z",
            "segments": [],
        }
        for index in range(session_count)
    ]
    for index in range(segment_count):
        session_index = min(session_count - 1, index * session_count // segment_count)
        sessions[session_index]["segments"].append(
            {
                "id": f"segment-{index}",
                "speaker": "Practitioner",
                "text": f"Synthetic transcript evidence {index} " + ("x" * 380),
                "startTime": index,
            }
        )
    return sessions


def _response(content="Concise supported evidence summary"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _client(side_effect=None):
    create = AsyncMock(side_effect=side_effect) if side_effect is not None else AsyncMock(return_value=_response())
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), create


def test_production_sized_history_is_partitioned_without_sampling_any_segment():
    sessions = _sessions()

    chunks = chunk_session_data(sessions, token_budget=12_000)

    retained_ids = [segment["id"] for chunk in chunks for segment in chunk.segments]
    assert retained_ids == [f"segment-{index}" for index in range(1_313)]
    assert all(chunk.estimated_tokens <= 12_000 for chunk in chunks)
    assert {chunk.session_id for chunk in chunks} == {f"session-{index}" for index in range(1, 9)}
    assert estimate_session_data_tokens(sessions) > 45_000


def test_multibyte_oversized_segment_stays_within_the_utf8_token_budget():
    sessions = _sessions(session_count=1, segment_count=1)
    sessions[0]["segments"][0]["text"] = "🧠" * 20_000

    chunks = chunk_session_data(sessions, token_budget=4_000)

    assert len(chunks) > 1
    assert all(chunk.estimated_tokens <= 4_000 for chunk in chunks)
    assert "".join(segment["text"] for chunk in chunks for segment in chunk.segments) == "🧠" * 20_000


def test_large_context_processes_every_section_and_reports_real_progress():
    sessions = _sessions(segment_count=320)
    client, create = _client()
    events = []

    result = asyncio.run(
        prepare_large_document_context(
            session_data=sessions,
            template={"name": "Progress report", "content": "Summarise progress and agreed actions."},
            openai_client=client,
            emit_progress=AsyncMock(side_effect=lambda event: events.append(event)),
            sleep=AsyncMock(),
        )
    )

    assert result.source_sessions == 8
    assert result.source_segments == 320
    assert result.source_sections == create.await_count
    assert result.segments
    completed = [event for event in events if event.get("details", {}).get("allSourcesProcessed")]
    assert completed[-1]["progress"] == {
        "current": result.source_sections,
        "total": result.source_sections,
    }
    prompts = "\n".join(
        call.kwargs["messages"][1]["content"] for call in create.await_args_list
    )
    assert "Synthetic transcript evidence 0" in prompts
    assert "Synthetic transcript evidence 319" in prompts


def test_section_summary_retries_a_rate_limit_and_keeps_the_user_informed():
    rate_limit = RuntimeError("busy")
    rate_limit.status_code = 429
    rate_limit.response = SimpleNamespace(headers={"retry-after": "1"})
    client, create = _client([rate_limit, _response("Recovered summary")])
    events = []
    sleep = AsyncMock()

    result = asyncio.run(
        _summarise_text(
            source_label="Session 1, section 1",
            source_text="Practitioner: synthetic evidence",
            template_name="Progress report",
            template_content="Summarise progress.",
            openai_client=client,
            emit_progress=AsyncMock(side_effect=lambda event: events.append(event)),
            sleep=sleep,
        )
    )

    assert result == "Recovered summary"
    assert create.await_count == 2
    sleep.assert_awaited_once_with(1.0)
    assert events[0]["stage"] == "waiting_for_capacity"
    assert events[0]["details"]["retryable"] is True


def test_retry_after_milliseconds_header_is_converted_to_seconds():
    rate_limit = RuntimeError("busy")
    rate_limit.response = SimpleNamespace(headers={"retry-after-ms": "1500"})

    assert _retry_after_seconds(rate_limit, attempt=0) == 1.5


def test_multi_session_endpoint_uses_hierarchical_full_source_path():
    sessions = _sessions(segment_count=180)
    request = SimpleNamespace(
        template={"id": "template-1", "name": "Progress report", "content": "Summarise progress."},
        sessionIds=[session["sessionId"] for session in sessions],
        sessionData=sessions,
        dictatedNotes=[],
        clientInfo={"id": "client-1", "name": "[CLIENT_NAME]"},
        practitionerInfo={"id": "profile-1", "name": "[PRACTITIONER_NAME]"},
        generationInstructions=None,
        generationId="generation-1",
    )
    progress = AsyncMock()
    prepared = LargeContextResult(
        segments=[{
            "transcript_id": "summary-1",
            "start_time": 0,
            "speaker": "Source summary",
            "text": "All synthetic source sections were processed.",
        }],
        source_sessions=8,
        source_segments=180,
        source_sections=8,
        reduction_levels=0,
    )
    generated = {
        "content": "Completed report",
        "generated_at": "2026-10-11T00:00:00Z",
        "metadata": {},
    }

    with (
        patch(
            "document_generation.agentic_endpoint.estimate_session_data_tokens",
            return_value=45_001,
        ),
        patch(
            "document_generation.agentic_endpoint.prepare_large_document_context",
            new=AsyncMock(return_value=prepared),
        ) as prepare,
        patch(
            "document_generation.agentic_endpoint.generate_document_from_context",
            new=AsyncMock(return_value=generated),
        ) as generate,
    ):
        result = asyncio.run(
            generate_document_from_template_agentic(
                request=request,
                http_request=SimpleNamespace(client=None, headers={}),
                authorization="Bearer synthetic",
                profileid="profile-1",
                openai_client=object(),
                emit_progress_func=progress,
                detect_policy_violation_func=AsyncMock(return_value={"is_violation": False}),
                log_violation_func=AsyncMock(),
            )
        )

    prepare.assert_awaited_once()
    generate.assert_awaited_once()
    assert result["content"] == "Completed report"
    assert result["metadata"]["processingMethod"] == "hierarchical_full_source"
    assert result["metadata"]["sourceCoverage"] == {
        "requestedSessions": 8,
        "processedSessions": 8,
        "processedSegments": 180,
        "processedSections": 8,
        "reductionLevels": 0,
        "allSourcesProcessed": True,
    }
