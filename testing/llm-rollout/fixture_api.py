"""Minimal synthetic Nest API surface for isolated Haystack rollout tests."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


PROFILE = os.getenv("FIXTURE_PROFILE_ID", "synthetic-profile")
TOKEN = os.getenv("FIXTURE_BEARER_TOKEN", "synthetic-scoped-token")
SERVICE_SECRET = os.getenv("HAYSTACK_WEBHOOK_SECRET", "")
EVENTS = []
SEGMENTS = [
    {
        "id": "segment-synthetic-1",
        "session_id": "session-synthetic-1",
        "transcript_id": "transcript-synthetic-1",
        "speaker": "Practitioner",
        "text": "The practitioner introduced paced breathing as a synthetic exercise.",
        "start_time": 0,
    },
    {
        "id": "segment-synthetic-2",
        "session_id": "session-synthetic-1",
        "transcript_id": "transcript-synthetic-1",
        "speaker": "Client",
        "text": "The synthetic client reported that paced breathing reduced stress.",
        "start_time": 12,
    },
]


def persona(name):
    temperatures = {"web_assistant": 0.7, "antsabot_therapist": 0.8, "antsabot_companion": 0.8}
    limits = {"web_assistant": 4096, "antsabot_therapist": 1024, "antsabot_companion": 1024}
    return {
        "version": 1,
        "name": f"Synthetic {name}",
        "description": "Synthetic rollout fixture; contains no client data.",
        "systemPrompt": "You are an isolated synthetic test persona. Never infer real client information.",
        "model": "gpt-5.2",
        "temperature": temperatures[name],
        "maxCompletionTokens": limits[name],
        "hasDbAccess": False,
        "toolNames": [],
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "antsa-synthetic-fixture/1"

    def log_message(self, pattern, *args):
        print(pattern % args, flush=True)

    def json_response(self, status, body):
        payload = json.dumps(body, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def caller_authorized(self):
        return (
            self.headers.get("Authorization") == f"Bearer {TOKEN}"
            and self.headers.get("ProfileID") == PROFILE
        )

    def service_authorized(self):
        return bool(SERVICE_SECRET) and self.headers.get("X-Haystack-Secret") == SERVICE_SECRET

    def do_GET(self):
        if self.path == "/health":
            self.json_response(200, {"status": "ready", "fixture": "synthetic"})
            return
        prefix = "/api/v1/ai/persona-configs/"
        if self.path.startswith(prefix):
            if not self.service_authorized():
                self.json_response(401, {"error": "invalid_service_secret"})
                return
            name = self.path[len(prefix):]
            if name not in {"web_assistant", "antsabot_therapist", "antsabot_companion"}:
                self.json_response(404, {"error": "persona_not_found"})
                return
            self.json_response(200, persona(name))
            return
        if self.path == "/_fixture/events":
            if not self.service_authorized():
                self.json_response(401, {"error": "invalid_service_secret"})
                return
            self.json_response(200, {"events": EVENTS})
            return
        self.json_response(404, {"error": "not_found"})

    def do_POST(self):
        if self.path in {
            "/api/v1/ai/transcripts/segments-by-sessions",
            "/api/v1/ai/semantic-search",
        }:
            if not self.caller_authorized():
                self.json_response(401, {"error": "invalid_synthetic_identity"})
                return
            body = self.read_json()
            session_ids = (
                body.get("session_ids")
                or body.get("transcript_ids")
                or [body.get("session_id")]
            )
            selected = [item for item in SEGMENTS if item["session_id"] in session_ids]
            self.json_response(200, {"segments": selected})
            return
        if self.path in {
            "/api/v1/ai/websocket/document-progress",
            "/api/v1/admin/policy-violations",
        }:
            if not (self.service_authorized() or self.caller_authorized()):
                self.json_response(401, {"error": "invalid_callback_identity"})
                return
            EVENTS.append({"path": self.path, "body": self.read_json()})
            self.json_response(200, {"accepted": True})
            return
        self.json_response(404, {"error": "not_found"})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
