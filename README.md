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
- `HAYSTACK_LLM_ROUTE_PREVIOUS_SESSION_SUMMARY` - Server-controlled route for
  durable previous-session summaries: `direct_openai` (default),
  `litellm_openai`, or `litellm_foundry`
- `LLM_GATEWAY_BASE_URL` - OpenAI-compatible LiteLLM URL ending in `/v1`; only
  required when the summary selects a LiteLLM route
- `HAYSTACK_LLM_GATEWAY_API_KEY` - Haystack-dedicated LiteLLM virtual key; never
  reuse the API service's gateway credential
- `HAYSTACK_LITELLM_MODEL_PREVIOUS_SESSION_SUMMARY_OPENAI` and
  `HAYSTACK_LITELLM_MODEL_PREVIOUS_SESSION_SUMMARY_FOUNDRY` - Stable gateway
  aliases for the selected summary provider
- `REDIS_URL` - Redis connection URL (optional)
- `MAX_CONCURRENT_REQUESTS` - Max concurrent requests (default: 100)
- `SESSION_TIMEOUT_MINUTES` - Session timeout (default: 30)

### Previous-session summary rollout

Only `POST /previous-session-summary` uses this route. Every chat, persona,
document-agent and conversation-summary client remains on its existing direct
OpenAI path.

1. Keep the route omitted or set it to `direct_openai` for the baseline.
2. Configure the base URL, Haystack-only virtual key and OpenAI alias, then set
   the route to `litellm_openai` and restart the service.
3. After its canary and burn-in, configure the Foundry alias and set the route
   to `litellm_foundry`.
4. Roll back only this workload by restoring its last validated route. There is
   no automatic cross-provider fallback or retry.

Invalid routes and missing selected gateway settings stop service startup. Safe
logs contain only workload, route, model alias, outcome and elapsed time; they
must never contain prompts, responses, transcripts, session IDs, credentials or
gateway URLs.

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
