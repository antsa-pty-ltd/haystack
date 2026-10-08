#!/usr/bin/env python3
"""Payload-safe live verification for the Haystack LiteLLM rollout.

Run this from an Azure Haystack worker with private gateway access.  The script
prints labels, status and timing only. It never prints request/response bodies,
credentials, URLs, model aliases, or generated fixture identifiers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, Callable


WORKLOADS = {
    "conversation_summary": "CONVERSATION_SUMMARY",
    "document_language": "DOCUMENT_LANGUAGE",
    "document_policy": "DOCUMENT_POLICY",
    "document_draft": "DOCUMENT_DRAFT",
    "document_agent": "DOCUMENT_AGENT",
    "chat": "CHAT",
    "web_assistant": "WEB_ASSISTANT",
    "therapist": "THERAPIST",
    "companion": "COMPANION",
    "transcriber": "TRANSCRIBER",
    "previous_session_summary": "PREVIOUS_SESSION_SUMMARY",
}

PERSONAS = {
    "web_assistant": "web_assistant",
    "therapist": "antsabot_therapist",
    "companion": "antsabot_companion",
    "transcriber": "transcriber_agent",
}


@dataclass
class Result:
    label: str
    layer: str
    outcome: str
    elapsed_ms: int = 0
    detail: str = ""


class VerificationError(RuntimeError):
    pass


def env(name: str, required: bool = True) -> str | None:
    value = os.getenv(name)
    if required and (value is None or not value.strip()):
        raise VerificationError(f"missing required environment variable: {name}")
    return value.strip() if value else None


def fixture_id() -> str:
    return f"rollout-{uuid.uuid4()}"


def synthetic_transcript(*, devanagari: bool = False, long: bool = False) -> str:
    text = (
        "Practitioner: What was useful in the planning exercise?\n"
        "Participant: Breaking the task into two small steps felt manageable.\n"
        "Practitioner: You chose to write the first step on a card before Friday.\n"
        "Participant: Yes. We did not discuss diagnosis, medication, or risk."
    )
    if devanagari:
        text += "\nParticipant: The accidental token was नमस्ते and should be rendered in English."
    if long:
        text = "\n".join(f"Segment {index}: {text}" for index in range(1, 31))
    return text


def request_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
    *,
    method: str = "POST",
) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json", **headers},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            body = response.read(2_000_000)
            status = response.status
    except urllib.error.HTTPError as error:
        try:
            error.read(2_000_000)
        finally:
            error.close()
        raise VerificationError(f"HTTP {error.code}") from None
    except (urllib.error.URLError, TimeoutError) as error:
        raise VerificationError(type(error).__name__) from None
    try:
        parsed = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise VerificationError("response was not valid JSON") from None
    if not isinstance(parsed, dict):
        raise VerificationError("response JSON was not an object")
    return status, parsed


def timed(label: str, layer: str, operation: Callable[[], None]) -> Result:
    started = time.monotonic()
    try:
        operation()
        return Result(label, layer, "PASS", int((time.monotonic() - started) * 1000))
    except Exception as error:
        # Only our deliberately sanitized errors may reach terminal output.
        detail = str(error) if isinstance(error, VerificationError) else type(error).__name__
        return Result(label, layer, "FAIL", int((time.monotonic() - started) * 1000), detail)


def gateway_probe(base_url: str, key: str, alias: str, workload: str, timeout: float) -> None:
    messages = [
        {"role": "system", "content": "Return the exact word OK. Do not call tools."},
        {"role": "user", "content": "Synthetic routing contract probe."},
    ]
    payload: dict[str, Any] = {
        "model": alias,
        "messages": messages,
        "temperature": 0,
        "max_completion_tokens": 256,
    }
    if workload == "previous_session_summary":
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "probe",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                },
            },
        }
        messages[0]["content"] = 'Return {"ok":true}.'
    elif workload == "document_policy":
        messages[0]["content"] = 'Return only {"is_violation":false}.'
    elif workload == "document_agent":
        payload["tools"] = [{
            "type": "function",
            "function": {
                "name": "synthetic_lookup",
                "description": "A synthetic no-side-effect lookup.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        }]
        payload["tool_choice"] = {"type": "function", "function": {"name": "synthetic_lookup"}}
    status, body = request_json(
        f"{base_url.rstrip('/')}/chat/completions",
        payload,
        {"Authorization": f"Bearer {key}"},
        timeout,
    )
    if status != 200 or not isinstance(body.get("choices"), list) or len(body["choices"]) != 1:
        raise VerificationError("completion contract failed")
    message = body["choices"][0].get("message")
    if not isinstance(message, dict):
        raise VerificationError("completion message contract failed")
    if workload == "previous_session_summary":
        try:
            content = json.loads(message.get("content") or "")
        except json.JSONDecodeError:
            raise VerificationError("strict JSON probe returned invalid content") from None
        if content != {"ok": True}:
            raise VerificationError("strict JSON probe returned wrong schema")
    elif workload == "document_policy":
        try:
            content = json.loads(message.get("content") or "")
        except json.JSONDecodeError:
            raise VerificationError("policy probe returned invalid JSON") from None
        if content != {"is_violation": False}:
            raise VerificationError("policy probe returned wrong contract")
    elif workload == "document_agent":
        calls = message.get("tool_calls")
        if not isinstance(calls, list) or len(calls) != 1:
            raise VerificationError("tool probe did not return one tool call")
        function = calls[0].get("function") if isinstance(calls[0], dict) else None
        if not isinstance(function, dict) or function.get("name") != "synthetic_lookup":
            raise VerificationError("tool probe returned the wrong tool")
        try:
            arguments = json.loads(function.get("arguments") or "")
        except json.JSONDecodeError:
            raise VerificationError("tool probe returned invalid arguments") from None
        if arguments != {}:
            raise VerificationError("tool probe returned unexpected arguments")
    elif (message.get("content") or "").strip() != "OK":
        raise VerificationError("completion probe did not return exact content")


def run_gateway(args: argparse.Namespace) -> list[Result]:
    base_url = env("LLM_GATEWAY_BASE_URL")
    key = env("HAYSTACK_LLM_GATEWAY_API_KEY")
    route = args.route.upper()
    results = []
    for workload, stem in WORKLOADS.items():
        alias = env(f"HAYSTACK_LITELLM_MODEL_{stem}_{route}")
        results.append(timed(
            f"gateway:{workload}",
            "gateway-direct",
            lambda alias=alias, workload=workload: gateway_probe(base_url, key, alias, workload, args.timeout),
        ))
    return results


def app_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {env('ROLL_OUT_API_BEARER_TOKEN')}",
        "profileid": env("ROLL_OUT_SYNTHETIC_PROFILE_ID"),
        "X-Haystack-Secret": env("HAYSTACK_WEBHOOK_SECRET"),
    }


def assert_chat(body: dict[str, Any]) -> None:
    for field in ("content", "message", "session_id", "message_id", "timestamp"):
        if not body.get(field):
            raise VerificationError(f"chat response missing {field}")


def run_chat_endpoint(base_url: str, persona: str, timeout: float) -> None:
    session: str | None = None
    headers = app_headers()
    try:
        for turn in (
            "Reply in one sentence: acknowledge this synthetic planning check.",
            "In one sentence, recall the planning topic from the previous turn.",
        ):
            _, body = request_json(
                f"{base_url}/chat",
                {"message": turn, "persona_type": persona, "session_id": session, "context": {"source": "rollout-verifier"}},
                headers,
                timeout,
            )
            previous_session = session
            candidate_session = body.get("session_id")
            if isinstance(candidate_session, str) and candidate_session:
                session = candidate_session
            assert_chat(body)
            if previous_session is not None and session != previous_session:
                raise VerificationError("second turn changed session")
    finally:
        if session:
            _, deleted = request_json(
                f"{base_url}/sessions/{urllib.parse.quote(session)}", {}, headers,
                min(timeout, 10), method="DELETE",
            )
            if deleted != {"deleted": True}:
                raise VerificationError("session cleanup contract failed")


def previous_summary(base_url: str, timeout: float) -> None:
    _, body = request_json(
        f"{base_url}/previous-session-summary",
        {"sessionId": fixture_id(), "recordingDate": "2026-01-15", "transcript": synthetic_transcript()},
        {"X-Haystack-Secret": env("HAYSTACK_WEBHOOK_SECRET")},
        timeout,
    )
    required = {"summary", "keyTopics", "homeworkStatus", "insights", "actionItems", "moodTrend"}
    if set(body) != required or body["moodTrend"] not in {"improving", "stable", "declining", "mixed", "unknown"}:
        raise VerificationError("strict six-field summary contract failed")


def conversation_summary(base_url: str, timeout: float) -> None:
    _, body = request_json(
        f"{base_url}/summarize-ai-conversations",
        {"conversations": [{
            "id": fixture_id(), "createdAt": "2026-01-15T01:00:00Z",
            "messages": [
                {"role": "user", "content": "I split a synthetic task into two steps."},
                {"role": "assistant", "content": "You chose to write down the first step."},
            ],
        }]},
        app_headers(),
        timeout,
    )
    if body.get("status") != "success" or not body.get("summary") or not isinstance(body.get("metadata"), dict):
        raise VerificationError("conversation summary product contract failed")


def document_payload(kind: str) -> dict[str, Any]:
    template_content = {
        "allowed": "Summarise topics discussed and actions explicitly agreed. Do not diagnose.",
        "blocked": "Determine whether the participant meets diagnostic criteria and provide a diagnosis.",
        "language": "Write an English session note. Preserve direct quotations exactly.",
        "refinement": (
            "ORIGINAL DOCUMENT:\n" + ("A synthetic observation was recorded. " * 80) +
            "\nREQUESTED MODIFICATIONS:\nShorten the document by 50%."
        ),
    }[kind]
    return {
        "template": {"id": fixture_id(), "name": f"Synthetic {kind} template", "content": template_content},
        "sessionIds": [fixture_id()],
        "sessionData": [{
            "id": fixture_id(),
            "segments": [{
                "id": fixture_id(), "transcript_id": fixture_id(), "start_time": index,
                "text": synthetic_transcript(devanagari=kind == "language"),
            } for index in range(4)],
        }],
        "dictatedNotes": [],
        "clientInfo": {"id": fixture_id(), "name": "[CLIENT_NAME]"},
        "practitionerInfo": {"id": fixture_id(), "name": "[PRACTITIONER_NAME]"},
        "generationInstructions": "Produce a concise note under 180 words." if kind not in {"blocked", "refinement"} else None,
        "generationId": fixture_id(),
    }


def document_generation(base_url: str, timeout: float, kind: str) -> None:
    _, body = request_json(
        f"{base_url}/generate-document-from-template",
        document_payload(kind),
        app_headers(),
        timeout,
    )
    if kind == "blocked":
        metadata = body.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("policyViolation") is not True:
            raise VerificationError("blocked policy response missing violation marker")
        if metadata.get("flagged") is not True or metadata.get("processingMethod") != "policy_violation_detected":
            raise VerificationError("blocked policy response has wrong domain contract")
        if not body.get("content") or not body.get("generatedAt"):
            raise VerificationError("blocked policy response is incomplete")
        return
    if not body.get("content") or not body.get("generatedAt") or not isinstance(body.get("metadata"), dict):
        raise VerificationError("document product contract failed")


def document_agent(base_url: str, timeout: float) -> None:
    session_ids = [item.strip() for item in (env("ROLL_OUT_DOCUMENT_SESSION_IDS") or "").split(",") if item.strip()]
    if not session_ids:
        raise VerificationError("missing required environment variable: ROLL_OUT_DOCUMENT_SESSION_IDS")
    payload = document_payload("allowed")
    payload["sessionIds"] = session_ids
    payload["sessionData"] = None
    _, body = request_json(
        f"{base_url}/generate-document-from-template", payload, app_headers(), timeout
    )
    if not body.get("content") or not isinstance(body.get("metadata"), dict):
        raise VerificationError("document agent product contract failed")


async def consume_stream(socket: Any, timeout: float) -> None:
    got_chunk = False
    async with asyncio.timeout(timeout):
        while True:
            event = json.loads(await socket.recv())
            event_type = event.get("type")
            if event_type == "message_chunk" and event.get("content"):
                got_chunk = True
            elif event_type == "message_error":
                raise VerificationError(f"stream terminal error: {event.get('code', 'unknown')}")
            elif event_type == "message_complete":
                if not got_chunk:
                    raise VerificationError("stream completed without content")
                return


async def stream_persona(base_url: str, persona: str, timeout: float) -> None:
    try:
        # The legacy client keeps the ``extra_headers`` contract across
        # websockets 13-16. The top-level client renamed it to
        # ``additional_headers`` in websockets 14, which made the verifier fail
        # before opening a socket on newer operator workstations.
        from websockets.legacy.client import connect as websocket_connect
    except ImportError:
        raise VerificationError("websockets package is required") from None
    profile_id = env("ROLL_OUT_SYNTHETIC_PROFILE_ID")
    _, created = await asyncio.to_thread(
        request_json,
        f"{base_url}/sessions",
        {"persona_type": persona, "context": {"source": "rollout-verifier"}},
        app_headers(),
        timeout,
    )
    session_id = created.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise VerificationError("session creation contract failed")
    ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://") + "/ws/" + urllib.parse.quote(session_id)
    headers = {
        "X-Haystack-Secret": env("HAYSTACK_WEBHOOK_SECRET"),
        "X-Haystack-Bridge-Type": "client-agent",
        "X-Profile-Id": profile_id,
    }
    try:
        async with asyncio.timeout(timeout):
            async with websocket_connect(ws_url, extra_headers=headers, open_timeout=min(timeout, 15)) as socket:
                first = json.loads(await socket.recv())
                if first.get("type") != "connection_established":
                    raise VerificationError("stream connection terminal missing")
                await socket.send(json.dumps({
                    "message": "Respond briefly to this synthetic no-tool planning check.",
                    "context": {"page_context": "dashboard", "source": "rollout-verifier", "propagate_errors": True},
                }))
                await consume_stream(socket, timeout)
    except TimeoutError:
        raise VerificationError("stream timed out before terminal event") from None
    finally:
        _, deleted = request_json(
            f"{base_url}/sessions/{urllib.parse.quote(session_id)}",
            {}, app_headers(), min(timeout, 10), method="DELETE",
        )
        if deleted != {"deleted": True}:
            raise VerificationError("session cleanup contract failed")


def run_application(args: argparse.Namespace) -> list[Result]:
    base_url = env("ROLL_OUT_HAYSTACK_BASE_URL").rstrip("/")
    results = [
        timed("application:previous_session_summary", "application-endpoint", lambda: previous_summary(base_url, args.timeout)),
        timed("application:conversation_summary", "application-endpoint", lambda: conversation_summary(base_url, args.timeout)),
    ]
    for label, persona in PERSONAS.items():
        results.append(timed(
            f"application:chat:{label}:two-turn",
            "application-endpoint",
            lambda persona=persona: run_chat_endpoint(base_url, persona, args.timeout),
        ))
    for label, persona in PERSONAS.items():
        results.append(timed(
            f"application:stream:{label}",
            "application-endpoint",
            lambda persona=persona: asyncio.run(stream_persona(base_url, persona, args.timeout)),
        ))
    results.append(timed(
        "application:document:initial-draft-policy-allowed",
        "application-endpoint",
        lambda: document_generation(base_url, args.document_timeout, "allowed"),
    ))
    results.append(timed(
        "application:document:shortening-refinement",
        "application-endpoint",
        lambda: document_generation(base_url, args.document_timeout, "refinement"),
    ))
    if os.getenv("ROLL_OUT_DOCUMENT_SESSION_IDS"):
        results.append(timed(
            "application:document:agent-tools",
            "application-endpoint-approved-fixture",
            lambda: document_agent(base_url, args.document_timeout),
        ))
    else:
        results.append(Result(
            "application:document:agent-tools",
            "application-endpoint-approved-fixture",
            "SKIP",
            detail="requires approved ROLL_OUT_DOCUMENT_SESSION_IDS",
        ))
    results.append(timed(
        "application:document:sourced-language-handling",
        "application-endpoint",
        lambda: document_generation(base_url, args.document_timeout, "language"),
    ))
    if args.allow_policy_write:
        results.append(timed(
            "application:document:policy-blocked",
            "application-endpoint-side-effect",
            lambda: document_generation(base_url, args.document_timeout, "blocked"),
        ))
    else:
        results.append(Result(
            "application:document:policy-blocked",
            "application-endpoint-side-effect",
            "SKIP",
            detail="requires --allow-policy-write and an approved disposable fixture",
        ))
    results.append(Result(
        "application:document:policy-fail-open",
        "isolated-fault-injection",
        "SKIP",
        detail="run the local isolated test; never break a live provider to prove fail-open",
    ))
    return results


def print_results(results: list[Result]) -> int:
    for result in results:
        suffix = f" ({result.elapsed_ms}ms)" if result.elapsed_ms else ""
        detail = f" - {result.detail}" if result.detail else ""
        print(f"{result.outcome:4} [{result.layer}] {result.label}{suffix}{detail}")
    passed = sum(result.outcome == "PASS" for result in results)
    failed = sum(result.outcome == "FAIL" for result in results)
    skipped = sum(result.outcome == "SKIP" for result in results)
    print(f"RESULT pass={passed} fail={failed} skip={skipped}")
    if failed:
        return 1
    return 3 if skipped else 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("gateway", "application", "all"), default="gateway")
    parser.add_argument("--route", choices=("openai", "foundry"), default="openai")
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--document-timeout", type=float, default=180)
    parser.add_argument("--allow-policy-write", action="store_true")
    parser.add_argument("--execute", action="store_true", help="Required acknowledgement before any live call")
    args = parser.parse_args(argv)
    if not args.execute:
        parser.error("live verification requires --execute")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        results: list[Result] = []
        if args.mode in {"gateway", "all"}:
            results.extend(run_gateway(args))
        if args.mode in {"application", "all"}:
            results.extend(run_application(args))
        return print_results(results)
    except VerificationError as error:
        print(f"CONFIG FAIL - {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
