from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

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
            return 200, {"choices": [{"message": {"content": "OK"}}]}

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

    def test_document_fixtures_are_deidentified_and_refinement_is_explicit(self):
        initial = VERIFY.document_payload("allowed")
        refinement = VERIFY.document_payload("refinement")
        serialized = json.dumps([initial, refinement])
        self.assertIn("[CLIENT_NAME]", serialized)
        self.assertIn("[PRACTITIONER_NAME]", serialized)
        self.assertIn("ORIGINAL DOCUMENT:", refinement["template"]["content"])
        self.assertIn("REQUESTED MODIFICATIONS:", refinement["template"]["content"])
        self.assertIn("Shorten the document by 50%", refinement["template"]["content"])

    def test_live_execution_requires_explicit_acknowledgement(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                VERIFY.parse_args(["--mode", "gateway"])


if __name__ == "__main__":
    unittest.main()
