# Haystack AI Service

A scalable AI chat service built with FastAPI and Haystack, designed to handle concurrent conversations with different AI personas.

## Features

- **Multiple AI Personas**: 
  - Web Assistant: AI assistant with clinic database access
  - Jaime Therapist: Compassionate therapist persona
- **Concurrent Processing**: Handles 100+ simultaneous conversations
- **WebSocket Streaming**: Real-time message streaming
- **Session Management**: Redis-backed session persistence with fallback
- **Scalable Architecture**: Async pipelines with Haystack

## Quick Start

1. **Setup Environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your OpenAI API key and other settings
   ```

2. **Start the Service**:
   ```bash
   ./start.sh
   ```

3. **Test the Service**:
   ```bash
   curl http://localhost:8001/health
   ```

## API Endpoints

### REST API

- `GET /health` - Health check
- `POST /sessions` - Create new chat session
- `GET /sessions/{session_id}/messages` - Get session messages
- `DELETE /sessions/{session_id}` - Delete session
- `POST /chat` - Send message (non-streaming)
- `GET /personas` - Get available personas
- `GET /stats` - Service statistics

### WebSocket

- `WS /ws/{session_id}` - Streaming chat connection

## Usage Examples

### Create Session
```bash
curl -X POST http://localhost:8001/sessions \
  -H "Content-Type: application/json" \
  -d '{"persona_type": "web_assistant", "context": {"page": "dashboard"}}'
```

### Send Message
```bash
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, how can you help me?", "persona_type": "web_assistant", "session_id": "your-session-id"}'
```

### WebSocket Connection
```javascript
const ws = new WebSocket('ws://localhost:8001/ws/your-session-id');
ws.send(JSON.stringify({
  type: 'chat_message',
  message: 'Hello!',
  persona_type: 'jaime_therapist'
}));
```

## Configuration

Environment variables in `.env`:

- `OPENAI_API_KEY` - OpenAI API key
- `HAYSTACK_LLM_ROUTE_*` - Server-controlled route per workload (see the table
  below): `direct_openai` (default), `litellm_openai`, or `litellm_foundry`
- `LLM_GATEWAY_BASE_URL` - OpenAI-compatible LiteLLM URL ending in `/v1`;
  required only when a workload selects a LiteLLM route
- `HAYSTACK_LLM_GATEWAY_API_KEY` - Haystack-dedicated LiteLLM virtual key; never
  reuse the API service's gateway credential
- `HAYSTACK_LITELLM_MODEL_<WORKLOAD>_OPENAI` and
  `HAYSTACK_LITELLM_MODEL_<WORKLOAD>_FOUNDRY` - Stable gateway aliases for the
  selected provider of each workload
- `REDIS_URL` - Redis connection URL (optional)
- `MAX_CONCURRENT_REQUESTS` - Max concurrent requests (default: 100)
- `SESSION_TIMEOUT_MINUTES` - Session timeout (default: 30)

### LLM workload routing

Every isolated LLM workload has its own route flag in `llm_routing.py`. All
routers are built and registered at service startup, and each flag defaults to
`direct_openai` when omitted, so an unset flag never changes call behaviour.

| Workload | Route flag | Direct model |
| --- | --- | --- |
| Chat (`POST /chat`) | `HAYSTACK_LLM_ROUTE_CHAT` | Runtime persona model |
| Web-assistant WebSocket pipeline | `HAYSTACK_LLM_ROUTE_WEB_ASSISTANT` | Runtime persona model |
| Therapist WebSocket pipeline | `HAYSTACK_LLM_ROUTE_THERAPIST` | Runtime persona model |
| Companion WebSocket pipeline | `HAYSTACK_LLM_ROUTE_COMPANION` | Runtime persona model |
| Transcriber WebSocket pipeline | `HAYSTACK_LLM_ROUTE_TRANSCRIBER` | Runtime persona model |
| Document exploration agent | `HAYSTACK_LLM_ROUTE_DOCUMENT_AGENT` | Caller-supplied (defaults to `gpt-5.2`) |
| Final document draft | `HAYSTACK_LLM_ROUTE_DOCUMENT_DRAFT` | `gpt-5.4-mini` |
| Document language repair | `HAYSTACK_LLM_ROUTE_DOCUMENT_LANGUAGE` | `gpt-5.4-mini` |
| Document policy check | `HAYSTACK_LLM_ROUTE_DOCUMENT_POLICY` | `gpt-4o-mini` (fails open) |
| Conversation summary | `HAYSTACK_LLM_ROUTE_CONVERSATION_SUMMARY` | `gpt-4o-mini` |
| Durable previous-session summary | `HAYSTACK_LLM_ROUTE_PREVIOUS_SESSION_SUMMARY` | `gpt-5.4-mini` |

Key behaviours:

- **Fail-fast startup**: invalid route values, missing gateway settings for a
  selected LiteLLM route, or malformed aliases stop service startup. A
  misconfiguration never surfaces mid-request.
- **No runtime fallback**: there is no automatic cross-provider retry or
  fallback. Rollback is a single workload flag change back to its last
  validated route, followed by a service restart.
- **Changes take effect on restart**: routes resolve at startup, and the four
  persona pipelines re-resolve again whenever a pipeline is rebuilt (for
  example when the persona model configuration changes).
- **Telemetry**: every workload emits payload-free `llm_workload_route_configured`
  and `llm_workload_call_completed` events containing only workload, route,
  model alias, outcome and elapsed time. Logs must never contain prompts,
  responses, transcripts, session IDs, credentials or gateway URLs.

Staged rollout guidance: move one workload at a time. Each workload first goes
to `litellm_openai` (proving the gateway path, with a canary and a rollback
window), and only after that burn-in completes does the same workload move to
`litellm_foundry`. Never flip two workloads merely because they share a model.

## Architecture

- **FastAPI**: High-performance async web framework
- **Haystack**: AI pipeline orchestration
- **Redis**: Session persistence (with in-memory fallback)
- **WebSockets**: Real-time streaming
- **OpenAI**: Language model provider

## Development

The fastest path is the dockerised stack in the sibling [`infra`](https://github.com/antsa-pty-ltd/infra) repo:

```bash
git clone git@github.com:antsa-pty-ltd/infra.git
./infra/dev/dev.sh up
```

Haystack runs on `:8001`. See [`infra/dev/README.md`](https://github.com/antsa-pty-ltd/infra/blob/develop/dev/README.md) for the full reference.

To run haystack standalone:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

Tests are scaffolded — `pytest` runs `test_integration.py`. A proper unit-test suite plus CI gate land in Sprint 3 (see `infra/docs/testing-journal.md`).

## Australian English

We use Australian spelling everywhere — colour, behaviour, organise, recognise, prioritise, analyse.

## Cross-repo development process

How we ship code across the four service repos, what's gated in CI, where to look when something breaks: see [**`infra/docs/development.md`**](https://github.com/antsa-pty-ltd/infra/blob/develop/docs/development.md).
# Trigger new deployment with updated secrets
