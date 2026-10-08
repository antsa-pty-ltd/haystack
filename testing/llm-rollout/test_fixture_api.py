import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

os.environ["HAYSTACK_WEBHOOK_SECRET"] = "fixture-service-secret"
os.environ["FIXTURE_BEARER_TOKEN"] = "fixture-token"
os.environ["FIXTURE_PROFILE_ID"] = "fixture-profile"

from fixture_api import Handler  # noqa: E402


class FixtureApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, path, *, method="GET", body=None, headers=None):
        request = urllib.request.Request(
            self.base + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)

    def test_health_and_persona_require_no_real_data(self):
        self.assertEqual(self.request("/health")[0], 200)
        status, body = self.request(
            "/api/v1/ai/persona-configs/web_assistant",
            headers={"X-Haystack-Secret": "fixture-service-secret"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["model"], "gpt-5.2")
        self.assertIn("Synthetic", body["name"])
        self.assertEqual(body["toolNames"], ["navigate_to_page", "get_client_summary"])

    def test_final_provider_defaults_use_gpt_5_4_tiers(self):
        defaults = {}
        for line in Path(__file__).with_name("defaults.env").read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                defaults[key] = value
        mini = {
            "OPENAI_HAYSTACK_PREVIOUS_SESSION_SUMMARY_MODEL",
            "OPENAI_HAYSTACK_CONVERSATION_SUMMARY_MODEL",
            "OPENAI_HAYSTACK_DOCUMENT_LANGUAGE_MODEL",
            "OPENAI_HAYSTACK_DOCUMENT_POLICY_MODEL",
            "OPENAI_HAYSTACK_DOCUMENT_DRAFT_MODEL",
        }
        full = {
            "OPENAI_HAYSTACK_DOCUMENT_AGENT_MODEL",
            "OPENAI_HAYSTACK_CHAT_MODEL",
            "OPENAI_HAYSTACK_WEB_ASSISTANT_MODEL",
            "OPENAI_HAYSTACK_THERAPIST_MODEL",
            "OPENAI_HAYSTACK_COMPANION_MODEL",
            "OPENAI_HAYSTACK_TRANSCRIBER_MODEL",
        }
        self.assertTrue(all(defaults[key] == "openai/gpt-5.4-mini" for key in mini))
        self.assertTrue(all(defaults[key] == "openai/gpt-5.4" for key in full))

    def test_exploration_requires_scoped_identity_and_returns_synthetic_segments(self):
        path = "/api/v1/ai/transcripts/segments-by-sessions"
        with self.assertRaises(urllib.error.HTTPError) as denied:
            self.request(path, method="POST", body={"session_ids": ["session-synthetic-1"]})
        self.assertEqual(denied.exception.code, 401)
        denied.exception.close()
        status, body = self.request(
            path,
            method="POST",
            body={"session_ids": ["session-synthetic-1"]},
            headers={"Authorization": "Bearer fixture-token", "ProfileID": "fixture-profile"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(body["segments"]), 2)
        self.assertTrue(all("synthetic" in segment["text"].lower() for segment in body["segments"]))


if __name__ == "__main__":
    unittest.main()
