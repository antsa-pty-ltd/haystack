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
- `REDIS_URL` - Redis connection URL (optional)
- `MAX_CONCURRENT_REQUESTS` - Max concurrent requests (default: 100)
- `SESSION_TIMEOUT_MINUTES` - Session timeout (default: 30)

## Architecture

- **FastAPI**: High-performance async web framework
- **Haystack**: AI pipeline orchestration
- **Redis**: Session persistence (with in-memory fallback)
- **WebSockets**: Real-time streaming
- **OpenAI**: Language model provider

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run with auto-reload
uvicorn main:app --reload --port 8001

# Run tests (TODO)
pytest
```