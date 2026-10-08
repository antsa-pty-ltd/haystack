from __future__ import annotations

import asyncio
import ast
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
from contextlib import redirect_stderr
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI, Request
from pydantic import BaseModel
from starlette.responses import JSONResponse

SCRIPT = Path(__file__).parents[1] / "scripts" / "verify-llm-rollout.py"
SPEC = importlib.util.spec_from_file_location("verify_llm_rollout", SCRIPT)
VERIFY = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class FakeSocket:
    def __init__(self, events):
        self.events = iter(events)

    async def recv(self):
        event = next(self.events)
        if isinstance(event, BaseException):
            raise event
        return json.dumps(event)


class VerifyRolloutTests(unittest.TestCase):
    def test_stream_requires_content_and_terminal_event(self):
        asyncio.run(VERIFY.consume_stream(FakeSocket([
            {"type": "typing"},
            {"type": "message_chunk", "content": "Synthetic reply"},
            {"type": "message_complete"},
        ]), 0.1))
        with self.assertRaisesRegex(VERIFY.VerificationError, "without content"):
            asyncio.run(VERIFY.consume_stream(FakeSocket([{"type": "message_complete"}]), 0.1))

    def test_stream_surfaces_sanitized_terminal_failure(self):
        with self.assertRaisesRegex(VERIFY.VerificationError, "AGENT_GENERATION_FAILED"):
            asyncio.run(VERIFY.consume_stream(FakeSocket([
                {"type": "message_error", "code": "AGENT_GENERATION_FAILED", "message": "sensitive upstream text"},
            ]), 0.1))

    def test_stream_timeout_is_bounded(self):
        class HangingSocket:
            async def recv(self):
                await asyncio.Event().wait()
        with self.assertRaises(TimeoutError):
            asyncio.run(VERIFY.consume_stream(HangingSocket(), 0.01))

    def test_gateway_probes_every_workload_without_exposing_secrets(self):
        environment = {
            "LLM_GATEWAY_BASE_URL": "https://private.example/v1",
            "HAYSTACK_LLM_GATEWAY_API_KEY": "do-not-print-key",
            **{f"HAYSTACK_LITELLM_MODEL_{stem}_OPENAI": f"secret-{workload}-alias"
               for workload, stem in VERIFY.WORKLOADS.items()},
        }
        calls = []

        def fake_request(url, payload, headers, timeout, **kwargs):
            calls.append((url, payload, headers))
            alias = payload["model"]
            if "previous_session_summary" in alias:
                message = {"content": '{"ok":true}'}
            elif "document_policy" in alias:
                message = {"content": '{"is_violation":false}'}
            elif "document_agent" in alias:
                message = {"content": None, "tool_calls": [{"function": {"name": "synthetic_lookup", "arguments": "{}"}}]}
            else:
                message = {"content": "OK"}
            return 200, {"choices": [{"message": message}]}

        with patch.dict(os.environ, environment, clear=True), patch.object(VERIFY, "request_json", fake_request):
            args = type("Args", (), {"route": "openai", "timeout": 1})()
            results = VERIFY.run_gateway(args)
        self.assertEqual(len(calls), len(VERIFY.WORKLOADS))
        self.assertEqual(len(calls), 11)
        self.assertTrue(all(result.outcome == "PASS" for result in results))
        rendered = "\n".join(f"{item.label} {item.detail}" for item in results)
        self.assertNotIn("do-not-print-key", rendered)
        self.assertNotIn("private.example", rendered)
        self.assertNotIn("secret-", rendered)
        self.assertEqual(calls[0][2]["Authorization"], "Bearer do-not-print-key")

    def test_gateway_rejects_empty_and_wrong_contracts(self):
        with patch.object(VERIFY, "request_json", return_value=(200, {"choices": [{"message": {"content": ""}}]})):
            with self.assertRaisesRegex(VERIFY.VerificationError, "exact content"):
                VERIFY.gateway_probe("https://gateway.test/v1", "key", "alias", "chat", 1)
        with patch.object(VERIFY, "request_json", return_value=(200, {"choices": [{"message": {"content": "OK"}}]})):
            with self.assertRaisesRegex(VERIFY.VerificationError, "tool call"):
                VERIFY.gateway_probe("https://gateway.test/v1", "key", "alias", "document_agent", 1)

    def test_http_failure_discards_provider_body(self):
        def fail(*_args, **_kwargs):
            raise VERIFY.urllib.error.HTTPError(
                "https://secret.example", 503, "bad", {}, io.BytesIO(b"provider-secret-payload")
            )

        with patch.object(VERIFY.urllib.request, "urlopen", fail):
            with self.assertRaises(VERIFY.VerificationError) as caught:
                VERIFY.request_json("https://secret.example", {}, {}, 1)
        self.assertEqual(str(caught.exception), "HTTP 503")

    def test_unexpected_exception_text_is_not_rendered(self):
        def fail():
            raise RuntimeError("secret URL and credential")

        result = VERIFY.timed("probe", "gateway-direct", fail)
        self.assertEqual(result.outcome, "FAIL")
        self.assertEqual(result.detail, "RuntimeError")

    def test_skipped_check_is_an_incomplete_nonzero_run(self):
        with patch("sys.stdout", io.StringIO()):
            self.assertEqual(VERIFY.print_results([VERIFY.Result("conditional", "isolated", "SKIP")]), 3)

    def test_document_fixtures_are_deidentified_and_refinement_is_explicit(self):
        initial = VERIFY.document_payload("allowed")
        refinement = VERIFY.document_payload("refinement")
        serialized = json.dumps([initial, refinement])
        self.assertIn("[CLIENT_NAME]", serialized)
        self.assertIn("[PRACTITIONER_NAME]", serialized)
        self.assertIn("ORIGINAL DOCUMENT:", refinement["template"]["content"])
        self.assertIn("REQUESTED MODIFICATIONS:", refinement["template"]["content"])
        self.assertIn("Shorten the document by 50%", refinement["template"]["content"])

    def test_blocked_policy_requires_exact_success_schema(self):
        environment = {
            "ROLL_OUT_API_BEARER_TOKEN": "token", "ROLL_OUT_SYNTHETIC_PROFILE_ID": "profile",
            "HAYSTACK_WEBHOOK_SECRET": "secret",
        }
        valid = {
            "content": "blocked", "generatedAt": "2026-01-01T00:00:00Z",
            "metadata": {"policyViolation": True, "flagged": True, "processingMethod": "policy_violation_detected"},
        }
        with patch.dict(os.environ, environment, clear=True), patch.object(VERIFY, "request_json", return_value=(200, valid)):
            VERIFY.document_generation("https://haystack.test", 1, "blocked")
        for invalid in (
            {"detail": "Invalid service credential"},
            {"content": "blocked", "generatedAt": "now", "metadata": {}},
        ):
            with patch.dict(os.environ, environment, clear=True), patch.object(VERIFY, "request_json", return_value=(200, invalid)):
                with self.assertRaises(VERIFY.VerificationError):
                    VERIFY.document_generation("https://haystack.test", 1, "blocked")

    def test_chat_two_turn_session_is_always_deleted_with_service_auth(self):
        environment = {
            "ROLL_OUT_API_BEARER_TOKEN": "token", "ROLL_OUT_SYNTHETIC_PROFILE_ID": "profile",
            "HAYSTACK_WEBHOOK_SECRET": "secret",
        }
        calls = []

        def fake_request(url, payload, headers, timeout, method="POST"):
            calls.append((url, payload, headers, method))
            if method == "DELETE":
                return 200, {"deleted": True}
            return 200, {
                "content": "reply", "message": "reply", "session_id": "opaque-session",
                "message_id": "opaque-message", "timestamp": "2026-01-01T00:00:00Z",
            }

        with patch.dict(os.environ, environment, clear=True), patch.object(VERIFY, "request_json", fake_request):
            VERIFY.run_chat_endpoint("https://haystack.test", "web_assistant", 1)
        self.assertEqual([call[3] for call in calls], ["POST", "POST", "DELETE"])
        self.assertTrue(all(call[2]["X-Haystack-Secret"] == "secret" for call in calls))

    def test_actual_routed_language_repair_uses_language_router(self):
        from document_generation.generator import generate_document_from_context
        from llm_routing import (
            DOCUMENT_DRAFT_WORKLOAD, DOCUMENT_LANGUAGE_WORKLOAD, LlmWorkloadRouter, router_registry,
        )

        bad = "[CLIENT_NAME] reported तनाव before a presentation."
        good = "[CLIENT_NAME] reported stress before a presentation."

        def client(output):
            value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=output), finish_reason="stop")])
            return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=value))))

        draft, language = client(bad), client(good)
        router_registry.clear()
        router_registry.register(LlmWorkloadRouter(
            workload=DOCUMENT_DRAFT_WORKLOAD, route_env="DRAFT_ROUTE", openai_alias_env="DRAFT_OPENAI",
            foundry_alias_env="DRAFT_FOUNDRY", direct_model="draft-model", direct_client=draft, environ={},
        ))
        router_registry.register(LlmWorkloadRouter(
            workload=DOCUMENT_LANGUAGE_WORKLOAD, route_env="LANGUAGE_ROUTE", openai_alias_env="LANGUAGE_OPENAI",
            foundry_alias_env="LANGUAGE_FOUNDRY", direct_model="language-model", direct_client=language, environ={},
        ))
        try:
            result = asyncio.run(generate_document_from_context(
                segments=[{"text": "I felt stress before a presentation.", "speaker": "Client"}],
                template={"content": "Write a brief note.", "name": "Synthetic"},
                client_info={"name": "[CLIENT_NAME]"}, practitioner_info={"name": "[PRACTITIONER_NAME]"},
                generation_instructions=None, openai_client=draft,
            ))
        finally:
            router_registry.clear()
        self.assertEqual(result["content"], good)
        self.assertEqual(draft.chat.completions.create.await_count, 1)
        self.assertEqual(language.chat.completions.create.await_count, 1)
        self.assertEqual(language.chat.completions.create.call_args.kwargs["model"], "language-model")

    def test_harness_payloads_match_real_fastapi_schemas_and_service_auth(self):
        source_root = Path(os.getenv(
            "HAYSTACK_CONTRACT_SOURCE",
            "/Users/alec/Projects/antsa/.worktrees/haystack-route-prereqs-20261008",
        ))
        source = (source_root / "main.py").read_text()
        tree = ast.parse(source)
        wanted = {"CreateSessionRequest", "ChatRequest", "GenerateDocumentRequest", "DictatedNote"}
        nodes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in wanted]
        self.assertEqual({node.name for node in nodes}, wanted)
        namespace = {"BaseModel": BaseModel, "Dict": Dict, "Any": Any, "Optional": Optional, "List": List}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source_root / "main.py"), "exec"), namespace)
        for name in wanted:
            namespace[name].model_rebuild(_types_namespace=namespace)

        route_paths = {
            decorator.args[0].value
            for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            for decorator in node.decorator_list if isinstance(decorator, ast.Call) and decorator.args
            and isinstance(decorator.args[0], ast.Constant) and isinstance(decorator.args[0].value, str)
        }
        self.assertTrue({"/sessions", "/chat", "/generate-document-from-template", "/summarize-ai-conversations"} <= route_paths)

        app = FastAPI()

        @app.middleware("http")
        async def service_auth(request: Request, call_next):
            if request.headers.get("x-haystack-secret") != "secret":
                return JSONResponse(status_code=401, content={"detail": "Invalid service credential"})
            return await call_next(request)

        def add_contract_route(path, model):
            async def endpoint(body):
                return {"ok": True}
            endpoint.__annotations__["body"] = model
            app.add_api_route(path, endpoint, methods=["POST"])

        add_contract_route("/sessions", namespace["CreateSessionRequest"])
        add_contract_route("/chat", namespace["ChatRequest"])
        add_contract_route("/generate-document-from-template", namespace["GenerateDocumentRequest"])

        async def exercise():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                headers = {"X-Haystack-Secret": "secret"}
                self.assertEqual((await client.post("/sessions", headers=headers, json={"persona_type": "web_assistant", "context": {}})).status_code, 200)
                self.assertEqual((await client.post("/chat", headers=headers, json={"message": "synthetic", "persona_type": "web_assistant"})).status_code, 200)
                self.assertEqual((await client.post("/generate-document-from-template", headers=headers, json=VERIFY.document_payload("allowed"))).status_code, 200)
                self.assertEqual((await client.post("/chat", json={"message": "synthetic"})).status_code, 401)
                self.assertEqual((await client.post("/generate-document-from-template", headers=headers, json={})).status_code, 422)

        asyncio.run(exercise())

    def test_live_execution_requires_explicit_acknowledgement(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                VERIFY.parse_args(["--mode", "gateway"])


if __name__ == "__main__":
    unittest.main()
