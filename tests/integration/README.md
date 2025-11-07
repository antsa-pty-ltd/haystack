# Haystack Backend Integration Tests

Comprehensive integration tests for the Haystack service backend, focusing on multi-component interactions with minimal mocking.

> **Latest Update (Phase 1)**: Enhanced test suite with WebSocket integration tests and policy violation payload validation. See [TEST_STATUS.md](TEST_STATUS.md) for details.
> **Current status: ✅ 59 passing, ⏭️ 28 skipped, ❌ 0 failed | 87 tests total | ⚡ 2.59s execution**

## Overview

These integration tests validate the interactions between backend components in the Haystack AI service:

- **FastAPI endpoints** ↔ WebSocket handling
- **SessionManager** ↔ Redis persistence
- **PipelineManager** ↔ OpenAI API ↔ Tool execution
- **ToolManager** ↔ NestJS API integration
- **UIStateManager** ↔ Redis (dual async/sync clients)
- **Policy enforcement** ↔ Async violation logging

## Testing Philosophy

**Principle**: Test behaviors and user-observable outcomes, not implementation details.

### Why Simpler Integration Tests?

Traditional integration tests for Haystack were too complex (15+ tool chains, deep mocking infrastructure) and brittle (broke on internal refactors). We've adopted a simpler approach:

1. **Focus on core flows**: Test essential functionality (auth, errors, API interactions)
2. **Minimal tool chains**: Use 2-3 tool sequences instead of 10-15
3. **Mock at system boundaries**: Mock NestJS API (external), not HTTP internals
4. **Test outcomes**: Verify what users see, not internal state

### Mock Strategy: httpx vs Implementation

**How we mock**:
- **Tools use httpx**: Tools make HTTP calls to NestJS API via `httpx.AsyncClient`
- **Mock httpx at the tool level**: Don't mock `httpx._mock` internals
- **Use helper functions**: `create_httpx_mock_response()` creates realistic httpx mocks
- **OpenAI mocking**: Use `MockOpenAIBuilder` for controllable responses

**What NOT to mock**:
- ❌ Internal Redis operations (use real Redis or let it fallback to in-memory)
- ❌ Session manager internals (test through public API)
- ❌ WebSocket protocol details (test message content, not frame structure)

**What to mock**:
- ✅ OpenAI API (expensive, rate-limited)
- ✅ NestJS API (external service)
- ✅ HTTP errors (5xx, 4xx responses)

### Example: Good vs Bad Patterns

**Bad Pattern** (too complex, brittle):
```python
# ❌ Testing 15-tool chain with intricate mocking
# - Tests break on internal refactors
# - Hard to understand what's being tested
# - No connection to real user behavior
async def test_complex_15_tool_chain():
    mock_openai = Mock()
    mock_openai.chat.completions.create = AsyncMock(...)  # 15 responses
    # ... 50 lines of setup ...
    # Tests: Specific tool order, internal state
```

**Good Pattern** (simple, maintainable):
```python
# ✅ Testing 2-tool chain with clear behavior
# - Tests user-observable behavior: auth propagation
# - Easy to understand in 20 lines
# - Survives internal refactors
async def test_auth_token_passed_to_tools():
    mock_openai = create_simple_tool_chain_mock([
        ("search_clients", {"query": "John"}),
        ("get_client_summary", {"client_id": "123"})
    ])
    # ... test that auth context is used ...
```

### Using Test Helpers

The `tests/helpers/` directory provides reusable utilities:

- **MockOpenAIBuilder**: Chainable builder for OpenAI responses + error simulation
- **MockNestJSAPIBuilder**: HTTP endpoint mocking
- **create_simple_tool_chain_mock()**: Quick 2-3 tool mock setup
- **create_httpx_mock_response()**: Realistic httpx.Response mocks
- **Decorators**: `@with_mock_session`, `@with_mock_pipeline` for setup
- **Assertion helpers**: `assert_tool_call_sequence()`, `assert_api_calls_made()`

See [test_core_functionality.py](backend/test_core_functionality.py) for usage examples.

## Directory Structure

```
tests/integration/
├── README.md (this file)
├── TEST_STATUS.md (detailed status and architectural review)
├── __init__.py
└── backend/
    ├── __init__.py
    ├── conftest.py                            # Shared fixtures (async_client, mock_openai)
    ├── test_core_functionality.py             # NEW: Simple core behavior tests ✨
    ├── test_extended_tool_chains.py           # P0: 10-15 tool chains ✅
    ├── test_redis_failover_scenarios.py       # P0: Redis failover + recovery ✅
    ├── test_session_recovery_advanced.py      # P0: Session TTL + reconnection ✅
    ├── test_rate_limiting_enforcement.py      # P1: Per-user rate limiting ✅
    ├── test_ui_state_synchronization.py       # P1: UI state + Redis sync ✅
    ├── test_error_recovery_flows.py           # P1: Error handling + recovery ✅
    ├── test_haystack_pipeline_integration.py  # P2: Haystack pipeline ✅
    ├── test_policy_violation_logging.py       # P2: Async violation logging ✅
    └── test_websocket_integration.py          # P0: WebSocket lifecycle + messaging ✅
```

**Removed files** (see TEST_STATUS.md for rationale):
- ~~test_auth_propagation_e2e.py~~ - Too complex, tested implementation details
- ~~test_document_generation_flow.py~~ - Too complex, tested implementation details

**New files** (Phase 2):
- `test_core_functionality.py` - Simple, maintainable tests for core behaviors

## Test Categories

### Priority 0 (P0) - Critical Flows

**These tests validate core functionality that must work for the system to be usable.**

#### 1. Extended Tool Chains ([test_extended_tool_chains.py](backend/test_extended_tool_chains.py)) ✅

**Purpose**: Validate complex multi-tool workflows (10-15 tools in sequence)

**Key Scenarios**:
- 15-tool chain with client_id auto-resolution
- Tool chain iteration limit enforcement (max 25)
- Tool deduplication within iterations
- Mid-chain error handling and recovery

**Status**: All tests passing

**Integration Points**:
- `PipelineManager` ↔ `ToolManager`
- `ToolManager` ↔ NestJS API
- `SessionManager` ↔ context persistence

**Example Flow**:
```
search_clients → get_client_summary → get_conversations →
load_session → analyze_session → check_document_readiness →
generate_document_auto
```

---

#### 2. ~~Document Generation Flow~~ ❌ REMOVED

**File**: `test_document_generation_flow.py` (removed after architectural review)

**Reason for removal**: Tested implementation details like system prompt construction and accumulated modification instructions. These tests made deep assumptions about internal OpenAI prompt formatting rather than testing behavior.

**Coverage maintained**: Policy violation detection is covered in `test_policy_violation_logging.py` (simplified).

See [TEST_STATUS.md](TEST_STATUS.md) for details.

---

#### 3. ~~Auth Propagation E2E~~ ❌ REMOVED

**File**: `test_auth_propagation_e2e.py` (removed after architectural review)

**Reason for removal**: Required extensive WebSocket mocking infrastructure that doesn't exist. Tested internal private functions like `_ensure_tools_context`. Made deep assumptions about WebSocket message handling flow.

**Coverage maintained**: Auth propagation is tested through actual tool execution in other integration tests.

See [TEST_STATUS.md](TEST_STATUS.md) for details.

---

#### 4. Redis Failover Scenarios ([test_redis_failover_scenarios.py](backend/test_redis_failover_scenarios.py)) ✅

**Purpose**: Validate in-memory fallback when Redis unavailable

**Key Scenarios**:
- Session creation when Redis down (uses in-memory)
- State recovery when Redis comes back
- Session operations work in both modes

**Status**: All tests passing

---

#### 5. WebSocket Integration ([test_websocket_integration.py](backend/test_websocket_integration.py)) ✅ **NEW**

**Purpose**: Validate WebSocket connection lifecycle and real-time message handling (main user interaction path)

**Key Scenarios**:
- **Connection Lifecycle**:
  - Connection establishment with session ID
  - Multiple concurrent connections (isolation)
  - Graceful disconnect handling
- **Heartbeat Mechanism**:
  - Heartbeat ping/pong acknowledged
  - Multiple heartbeats maintain connection
- **UI State Updates**:
  - Full state update delivery via WebSocket
  - Incremental state updates with timestamp ordering
  - State updates work without auth token (initial state)
- **Chat Messages**:
  - Typing indicator triggered on message send
  - Message streaming in chunks
  - Message completion signal sent
  - Empty messages ignored gracefully
- **UI Actions**:
  - UI actions delivered after AI response
- **Error Handling**:
  - Invalid JSON causes disconnect (expected FastAPI behavior)
  - Message processing errors return error messages
- **Auth Context**:
  - Auth token extracted from messages and used
  - ProfileID included in auth context

**Integration Points**:
- FastAPI WebSocket endpoint `/ws/{session_id}`
- `SessionManager` ↔ WebSocket connection state
- `UIStateManager` ↔ Real-time state sync
- Auth token/ProfileID extraction and propagation

**Test Structure** (17 tests, 16 passing, 1 skipped):
```
TestWebSocketConnection (3 tests)
├── test_websocket_connection_establishment
├── test_websocket_multiple_concurrent_connections
└── test_websocket_disconnect_handling

TestWebSocketHeartbeat (2 tests)
├── test_heartbeat_acknowledged
└── test_multiple_heartbeats

TestWebSocketUIStateUpdates (3 tests)
├── test_full_ui_state_update
├── test_incremental_ui_state_update
└── test_ui_state_update_without_auth_token

TestWebSocketChatMessages (4 tests)
├── test_chat_message_triggers_typing_indicator
├── test_chat_message_streaming_chunks
├── test_chat_message_completion_signal
└── test_empty_message_ignored

TestWebSocketUIActions (1 test)
└── test_ui_actions_delivered_after_response

TestWebSocketErrorHandling (2 tests)
├── test_invalid_json_handled (skipped - expected FastAPI behavior)
└── test_message_processing_error_returns_error_message

TestWebSocketAuthContext (2 tests)
├── test_auth_token_from_message_used
└── test_profile_id_included_in_context
```

**Message Types Tested**:
- `connection_established`: Initial connection confirmation
- `heartbeat`: Keep-alive mechanism
- `full_state_update`: Complete UI state sync
- `incremental_state_update`: Partial state changes
- `typing_indicator`: User activity feedback
- `text_chunk`: Streaming AI responses
- `message_complete`: Response completion
- `ui_actions`: Post-response UI updates
- `error`: Error feedback to client

**Status**: 16 passing, 1 skipped (expected behavior documented)

---

#### 6. Policy Violation Logging ([test_policy_violation_logging.py](backend/test_policy_violation_logging.py)) ✅

**Purpose**: Validate async logging of policy violations to NestJS API

**Key Scenarios**:
- Violation logged to `/admin/policy-violations`
- Log includes request metadata (IP, User-Agent)
- Multiple violations logged separately
- Logging failure doesn't block user response
- Missing profile_id skips logging gracefully

**Integration Points**:
- FastAPI ↔ OpenAI (policy detection)
- `asyncio.create_task()` for non-blocking logging
- HTTP POST to NestJS API
- Error handling for logging failures

**Violation Data Structure**:
```json
{
  "profile_id": "profile_123",
  "template_id": "template_456",
  "template_name": "Diagnostic Assessment",
  "violation_type": "medical_diagnosis_request",
  "template_content": "...",
  "reason": "Template requests DSM-5 diagnosis",
  "confidence": "high",
  "client_id": "client_789",
  "metadata": {
    "timestamp": "2024-01-15T10:00:00Z",
    "generationInstructions": "..."
  },
  "ip_address": "127.0.0.1",
  "user_agent": "Mozilla/5.0..."
}
```

---

### Priority 1 (P1) - Important Flows

**These tests validate important system behavior and resilience.**

#### 7. Rate Limiting Enforcement ([test_rate_limiting_enforcement.py](backend/test_rate_limiting_enforcement.py))

**Purpose**: Validate per-user concurrent request limits

**Key Scenarios**:
- 8 concurrent requests within limit (all process)
- 15 concurrent requests (10 process, 5 queue)
- Multiple users have independent limits
- 50 concurrent users stress test
- Semaphore cleanup after requests

**Configuration**:
- Max requests per user: 10 (configurable via `settings.max_requests_per_user`)
- Uses `asyncio.Semaphore` per user
- Inactive semaphores cleaned up periodically

---

#### 8. UI State Synchronization ([test_ui_state_synchronization.py](backend/test_ui_state_synchronization.py))

**Purpose**: Validate UI state management and Redis sync

**Key Scenarios**:
- Full state update via WebSocket
- Incremental update with timestamp ordering
- Stale update rejection (older timestamps)
- Async update ↔ sync read coordination
- State persists after WebSocket disconnect

**Dual Client Architecture**:
- **Async client**: Used by FastAPI WebSocket handlers
- **Sync client**: Used by tool execution (avoids event loop conflicts)
- Both clients access same Redis keys

---

### Priority 2 (P2) - Edge Cases

**These tests validate edge cases and alternative implementations.**

#### 9. Error Recovery Flows ([test_error_recovery_flows.py](backend/test_error_recovery_flows.py))

**Purpose**: Validate error handling and graceful degradation

**Key Scenarios**:
- OpenAI timeout handling (>120s)
- OpenAI rate limit errors
- NestJS API completely down
- WebSocket disconnect during tool execution
- Tool chain continues after single tool failure
- Session integrity under errors

**Error Handling Principles**:
- Non-blocking: Errors don't cascade
- Graceful degradation: Partial results returned
- User-facing: Clear error messages
- Session preservation: State remains valid

---

#### 10. Haystack Pipeline Integration ([test_haystack_pipeline_integration.py](backend/test_haystack_pipeline_integration.py))

**Purpose**: Validate Haystack-based pipeline (alternative to legacy)

**Key Scenarios**:
- Pipeline initialization with Haystack components
- Tool execution via `ToolInvoker`
- Multi-tool chaining via `ConditionalRouter`
- Comparison with legacy pipeline (same prompts)
- UI action extraction from tool results

**Haystack Components**:
- `OpenAIChatGenerator`: Chat completion with streaming
- `ToolInvoker`: Execute tools from function definitions
- `ConditionalRouter`: Route based on tool_calls presence
- Iterative agent loop (max 25 iterations)

**Note**: 13 of 17 tests currently skipped pending Haystack pipeline completion

---

## Running Tests

### Run All Integration Tests

```bash
cd haystack
pytest tests/integration/ -v
```

### Run Specific Priority

```bash
# P0 tests only
pytest tests/integration/backend/test_extended_tool_chains.py \
       tests/integration/backend/test_document_generation_flow.py \
       tests/integration/backend/test_auth_propagation_e2e.py \
       tests/integration/backend/test_policy_violation_logging.py \
       -v

# P1 tests
pytest tests/integration/backend/test_redis_failover_scenarios.py \
       tests/integration/backend/test_session_recovery_advanced.py \
       tests/integration/backend/test_rate_limiting_enforcement.py \
       tests/integration/backend/test_ui_state_synchronization.py \
       -v

# P2 tests
pytest tests/integration/backend/test_haystack_pipeline_integration.py \
       tests/integration/backend/test_error_recovery_flows.py \
       -v
```

### Run Specific Test File

```bash
pytest tests/integration/backend/test_auth_propagation_e2e.py -v
```

### Run Specific Test Class or Method

```bash
# Run specific test class
pytest tests/integration/backend/test_extended_tool_chains.py::TestExtendedToolChains -v

# Run specific test method
pytest tests/integration/backend/test_auth_propagation_e2e.py::TestAuthPropagationFullStack::test_websocket_to_nestjs_api_auth_flow -v
```

### Run with Coverage

```bash
pytest tests/integration/ --cov=. --cov-report=html --cov-report=term
```

---

## Test Environment Setup

### Prerequisites

1. **Redis** (optional - tests use in-memory fallback if unavailable)
   ```bash
   redis-server
   ```

2. **Environment Variables** (`.env` file)
   ```env
   OPENAI_API_KEY=sk-test-key-12345
   REDIS_URL=redis://localhost:6379
   NESTJS_API_URL=http://localhost:3000/api/v1
   SESSION_TIMEOUT_MINUTES=240
   ```

3. **Install Test Dependencies**
   ```bash
   pip install -r requirements-test.txt
   ```

### Mock vs Real Services

**Mocked by Default**:
- OpenAI API (to avoid costs and rate limits)
- NestJS API (HTTP responses mocked)
- Redis (optional - uses in-memory fallback)

**Real Services** (if available):
- Redis connection (if `REDIS_URL` accessible)
- Session manager (uses real Redis if available)
- UI state manager (uses real Redis if available)

---

## Architecture Overview

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                        FastAPI App                          │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  WebSocket Endpoint                                   │  │
│  │  - Receives auth_token, profile_id                    │  │
│  │  - Handles chat_message, ui_state_update, heartbeat  │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  HTTP Endpoints                                       │  │
│  │  - POST /sessions (create session)                    │  │
│  │  - POST /generate-document-from-template             │  │
│  │  - POST /summarize-ai-conversations                  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          ↓
        ┌─────────────────┼─────────────────┐
        ↓                 ↓                 ↓
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ SessionMgr   │  │ UIStateMgr   │  │ PipelineMgr  │
│              │  │              │  │              │
│ - Redis      │  │ - Redis      │  │ - OpenAI     │
│ - 4h TTL     │  │ - 24h TTL    │  │ - Streaming  │
│ - Fallback   │  │ - Dual client│  │ - Tools      │
└──────────────┘  └──────────────┘  └──────────────┘
        ↓                 ↓                 ↓
        └─────────────────┼─────────────────┘
                          ↓
                  ┌──────────────┐
                  │ ToolManager  │
                  │              │
                  │ - 40+ tools  │
                  │ - Auth ctx   │
                  │ - NestJS API │
                  └──────────────┘
                          ↓
                  ┌──────────────┐
                  │ NestJS API   │
                  │              │
                  │ - Clients    │
                  │ - Sessions   │
                  │ - Templates  │
                  │ - Violations │
                  └──────────────┘
```

### Critical Integration Points

| Integration | Description | Tests |
|-------------|-------------|-------|
| **WebSocket ↔ FastAPI** | Connection lifecycle, real-time messaging | P0: test_websocket_integration.py ✅ NEW |
| **WebSocket ↔ Session** | Auth extraction and storage | P0: test_websocket_integration.py (auth context) |
| **Session ↔ Redis** | Persistence with TTL | P0: test_session_recovery_advanced.py |
| **Pipeline ↔ OpenAI** | Streaming with tools | P0: test_extended_tool_chains.py |
| **Pipeline ↔ Tools** | Multi-tool chaining | P0: test_extended_tool_chains.py |
| **Tools ↔ NestJS API** | HTTP requests with auth | P0: test_extended_tool_chains.py |
| **FastAPI ↔ Policy Check** | Async violation logging | P0: test_policy_violation_logging.py |
| **UIState ↔ Redis** | Dual client sync | P1: test_ui_state_synchronization.py |
| **UIState ↔ WebSocket** | Real-time state updates | P0: test_websocket_integration.py (UI state) |
| **Redis Failover** | In-memory fallback | P0: test_redis_failover_scenarios.py |

---

## Writing New Integration Tests

### Test Structure Template

```python
"""
Test File Name: test_new_feature_integration.py

Brief description of what this test file validates.

Integration Points:
- Component A ↔ Component B
- Component C ↔ External Service

Test Categories:
- Happy path
- Error scenarios
- Edge cases
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class TestNewFeatureBasics:
    """Tests for basic functionality"""

    async def test_happy_path(self):
        """
        Test the main happy path scenario.

        Flow:
        1. Setup preconditions
        2. Execute action
        3. Verify results

        This tests:
        - Primary functionality
        - Expected behavior
        """
        # Arrange
        from module_under_test import component

        # Act
        result = await component.method()

        # Assert
        assert result is not None


class TestNewFeatureErrors:
    """Tests for error handling"""

    async def test_error_scenario(self):
        """Test error handling"""
        pytest.skip("Implementation pending")
```

### Best Practices

1. **Use Descriptive Names**: Test names should clearly describe what is being tested
2. **Document Flow**: Include flow diagram or step-by-step description
3. **Minimal Mocking**: Only mock external services (OpenAI, NestJS API)
4. **Clean Up Resources**: Use `try/finally` to clean up sessions, connections
5. **Isolate Tests**: Each test should be independent (no shared state)
6. **Use Fixtures**: Leverage `conftest.py` fixtures for common setup
7. **Test Edge Cases**: Don't just test happy paths
8. **Verify Full Stack**: Integration tests should exercise multiple components

### Common Fixtures (from `conftest.py`)

- `async_client`: FastAPI test client
- `test_session_id`: Auto-cleanup session
- `mock_openai`: Mocked OpenAI with smart responses
- `mock_nestjs_api`: Mocked NestJS API
- `mock_tool_manager`: Mocked tool manager
- `session_factory`: Helper for creating multiple sessions
- `sample_*`: Sample data (templates, transcripts, client info)

---

## Maintenance

### When to Update Tests

- **New API endpoint**: Add integration test
- **New tool added**: Add to tool chain tests
- **Architecture change**: Update affected integration tests
- **Bug fix**: Add regression test

### Test Health Checks

```bash
# Run all tests and check status
pytest tests/integration/ -v --tb=short

# Check for skipped tests
pytest tests/integration/ -v -rs

# Check coverage
pytest tests/integration/ --cov=. --cov-report=term-missing
```

---

## Troubleshooting

### Common Issues

**Redis Connection Errors**:
```
ConnectionError: Error 111 connecting to localhost:6379
```
- Solution: Tests will fallback to in-memory storage automatically
- Optional: Start Redis with `redis-server`

**OpenAI API Key Not Set**:
```
AssertionError: OPENAI_API_KEY environment variable not set
```
- Solution: Tests use mocked OpenAI by default
- Set dummy key: `export OPENAI_API_KEY=sk-test-key`

**Import Errors**:
```
ImportError: No module named 'haystack'
```
- Solution: Install dependencies: `pip install -r requirements.txt`

### Debug Mode

Run tests with verbose output and no capture:
```bash
pytest tests/integration/backend/test_auth_propagation_e2e.py -v -s --log-cli-level=DEBUG
```

---

## Related Documentation

- [Main Test README](../README.md) - Overview of all tests
- [Testing Guide](../TESTING_GUIDE.md) - Comprehensive testing documentation
- [CLAUDE.md](../../CLAUDE.md) - Project architecture overview

---

## Advanced Testing Scenarios (Manual/Future Automation)

The following scenarios are too complex for automated integration tests or require specialized infrastructure. They are documented here for manual testing and future automation efforts.

### Concurrent Multi-User Load Testing

**Why not automated**: Requires significant infrastructure, non-deterministic results, and specialized load testing tools.

**Manual testing approach**:
1. Start Haystack service: `python main.py`
2. Create load test script using locust or similar:
   ```python
   from locust import HttpUser, task, between

   class HaystackUser(HttpUser):
       wait_time = between(1, 3)

       @task
       def create_session_and_chat(self):
           # Create session
           session = self.client.post("/sessions", json={"persona_type": "web_assistant"})
           session_id = session.json()["session_id"]

           # Connect WebSocket and send messages
           # (WebSocket testing in locust requires plugin)
   ```
3. Run load test: `locust -f locustfile.py --users 50 --spawn-rate 5`
4. Monitor metrics:
   - Redis connections: `redis-cli info clients`
   - Memory usage: `htop` or `top`
   - Response times in locust dashboard
   - Per-user semaphore counts (internal logging)

**Expected behavior**:
- 50 concurrent users, each with up to 10 concurrent requests = 500 max concurrent
- Sessions isolated by user (no cross-user data leakage)
- Redis handles connection pooling without exhaustion
- No memory leaks over extended periods (run for 1+ hours)
- Rate limiting enforced per user (11th request queues)

**Key metrics to track**:
- Average response latency: < 2 seconds for simple queries
- P95 response latency: < 5 seconds
- Error rate: < 1%
- Memory per session: < 5MB
- Redis memory growth: Linear with session count, not time

---

### End-to-End Testing with Real Services

**Why not automated**: Expensive (OpenAI API costs), requires full stack, flaky due to external dependencies.

**Manual testing approach**:

1. **Set up full stack**:
   ```bash
   # Terminal 1: Redis
   redis-server

   # Terminal 2: NestJS API
   cd api && npm run dev

   # Terminal 3: Haystack
   cd haystack && python main.py
   ```

2. **Create real session via HTTP**:
   ```bash
   curl -X POST http://localhost:8001/sessions \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer <real-token>" \
     -d '{"persona_type": "web_assistant"}'
   ```

3. **Connect via WebSocket** (using `wscat` or similar):
   ```bash
   wscat -c ws://localhost:8001/ws/<session_id>

   # Send chat message
   {"type": "chat_message", "content": "Find all clients named John", "auth_token": "<token>"}
   ```

4. **Verify**:
   - Tool execution calls real NestJS API
   - OpenAI returns real responses (costs money!)
   - UI actions sent back via WebSocket
   - Redis persists session state
   - WebSocket disconnects handled gracefully

**Use pytest markers for partial real testing**:
```bash
# Test with real Redis but mocked OpenAI/NestJS
pytest tests/integration/ -m requires_redis

# Test with real OpenAI (expensive, skipped by default)
pytest tests/integration/ -m real_ai
```

**Cost estimation**:
- Simple query (no tools): ~$0.01 per test
- Complex query (5+ tools): ~$0.05 per test
- Full E2E test suite with real AI: ~$5-10

---

### Thread Safety and Event Loop Edge Cases

**Why not automated**: Very low-level, hard to reproduce consistently, requires deep runtime inspection.

**What to test manually**:

1. **Sync UI state methods from multiple threads**:
   - Call `get_state_sync()` from 10 threads simultaneously
   - Verify no "different event loop" errors
   - Use threading library + pytest

2. **Tool execution from Haystack ToolInvoker**:
   - ToolInvoker runs in thread pool (Haystack behavior)
   - Tools use `asyncio.run_coroutine_threadsafe()` to bridge
   - Monitor for event loop warnings in logs

3. **Redis sync client during async operations**:
   - Main event loop uses async Redis client
   - Tool threads use sync Redis client
   - Both access same keys without conflicts

4. **asyncio.run_coroutine_threadsafe() edge cases**:
   - Tool execution from non-main thread
   - Multiple concurrent tool executions
   - Tool timeouts and cancellation

**Known working patterns**:
- `UIStateManager` uses dual Redis clients (async + sync)
- Tools use `redis_client_sync` when called from threads
- Pipeline uses `redis_client` (async) in main event loop
- No shared state between threads except Redis

**How to test**:
```python
import threading
import asyncio
from ui_state_manager import UIStateManager

def test_thread_safety():
    ui_manager = UIStateManager()
    asyncio.run(ui_manager.initialize())

    def worker(i):
        # Call sync method from thread
        state = ui_manager.get_state_sync(f"session-{i}")
        assert state is not None

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
```

---

### Performance and Memory Profiling

**Why not automated**: Requires specialized tools, long-running tests, and manual analysis.

**Tools and approach**:

1. **Memory profiling with memory_profiler**:
   ```bash
   pip install memory_profiler
   python -m memory_profiler main.py

   # Add @profile decorator to functions
   @profile
   def generate_response(...):
       ...
   ```

2. **CPU profiling with py-spy**:
   ```bash
   pip install py-spy
   py-spy top -- python main.py

   # Or record flame graph
   py-spy record -o profile.svg -- python main.py
   ```

3. **Redis monitoring**:
   ```bash
   redis-cli --stat
   redis-cli info memory
   redis-cli --bigkeys
   ```

4. **Load testing with locust** (see Concurrent Multi-User section)

**Key metrics**:

| Metric | Target | Red Flag |
|--------|--------|----------|
| Requests per second per user | > 5 | < 2 |
| Average response latency | < 2s | > 5s |
| P95 response latency | < 5s | > 10s |
| Memory per session | < 5MB | > 20MB |
| Redis memory (100 sessions) | < 500MB | > 2GB |
| OpenAI API latency | < 1s | > 3s |
| Session cleanup (TTL 4h) | Automatic | Manual required |

**Memory leak detection**:
1. Start service
2. Create 1000 sessions
3. Monitor memory every 10 minutes for 2 hours
4. Memory should:
   - Increase with active sessions (normal)
   - Decrease as sessions expire (4-hour TTL)
   - Stabilize after cleanup
   - NOT grow indefinitely with constant session count

**Profiling commands**:
```bash
# CPU profile
py-spy record -o profile.svg --pid $(pgrep -f "python main.py")

# Memory snapshot
python -c "import gc; gc.collect(); import objgraph; objgraph.show_most_common_types(limit=20)"
```

---

### Security Testing

**Why not automated**: Requires security expertise, ethical considerations, and specialized tools.

**Areas to test**:

1. **Auth token validation and expiration**:
   - Expired JWT tokens rejected
   - Malformed tokens handled gracefully
   - Missing Authorization header returns 401
   - Token replay attacks prevented

2. **Profile ID spoofing attempts**:
   - User A cannot access User B's data
   - ProfileID header validated against token
   - Session isolation enforced

3. **SQL injection in tool parameters**:
   - NestJS API side (test via tool execution)
   - Example: `search_clients(search_term="'; DROP TABLE clients;--")`
   - Should be parameterized queries, not string concatenation

4. **WebSocket message validation**:
   - Malformed JSON rejected
   - Oversized messages rejected (DoS prevention)
   - Unknown message types handled gracefully

5. **Rate limiting bypass attempts**:
   - Verify per-user rate limit enforced
   - Multiple connections from same user share limit
   - Cannot bypass with different session IDs

6. **Session hijacking scenarios**:
   - Session ID guessing (UUIDs should be unguessable)
   - Session reuse across different users
   - Session persistence across auth token changes

**Use security scanning tools**:

```bash
# API security scan with OWASP ZAP
zap-cli quick-scan http://localhost:8001

# Python security issues with bandit
bandit -r . -ll

# Dependency vulnerabilities
pip-audit
```

**Manual penetration testing**:
- Use Burp Suite or similar
- Test each endpoint with invalid/malicious inputs
- Monitor logs for security warnings
- Document findings and remediation

---

## Contributing

When adding new integration tests:

1. **Identify Integration Points**: What components interact?
2. **Define Test Scope**: What scenarios to cover?
3. **Write Tests**: Follow template and best practices
4. **Document**: Add docstrings and flow descriptions
5. **Verify**: Run tests and check coverage
6. **Update README**: Add test to this document

---

**Last Updated**: 2025-11-06
**Test Coverage**: Backend integration flows + Advanced scenarios documented
**Priority**: P0 (Critical), P1 (Important), P2 (Edge Cases)
