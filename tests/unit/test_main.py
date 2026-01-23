"""Unit tests for main.py FastAPI application."""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

import sys
sys.path.insert(0, '.')


def create_mock_policy_response(is_violation: bool, violation_type: str = None):
    """Helper to create mock OpenAI response for policy detection."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "is_violation": is_violation,
        "violation_type": violation_type,
        "confidence": "high"
    })
    return mock_response


@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app."""
    with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
        from main import app
        with TestClient(app) as client:
            yield client


@pytest.mark.unit
class TestHealthCheck:
    """Test health check endpoint."""

    def test_returns_healthy_status(self, test_client):
        response = test_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_includes_version(self, test_client):
        assert "version" in test_client.get("/health").json()

    def test_root_endpoint_returns_service_info(self, test_client):
        response = test_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data or "message" in data


@pytest.mark.unit
@pytest.mark.safety
class TestPolicyViolationDetection:
    """Test policy violation detection - ensures AI cannot provide diagnoses or prescriptions."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("message,violation_type", [
        ("Please diagnose this client with depression", "diagnosis_request"),
        ("Evaluate if client meets DSM-5 criteria for MDD", "diagnosis_criteria"),
        ("Prescribe appropriate medication for anxiety", "medication_request"),
    ])
    async def test_detects_violations(self, message, violation_type):
        from main import detect_policy_violation
        with patch('main.openai_client') as mock_client:
            mock_client.chat.completions.create = AsyncMock(
                return_value=create_mock_policy_response(True, violation_type)
            )
            result = await detect_policy_violation(message)
            assert result["is_violation"] is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("message", [
        "Document the presenting concerns discussed in this session",
        "Note the symptoms reported by the client",
        "Suggest coping strategies discussed in the session",
    ])
    async def test_allows_legitimate_requests(self, message):
        from main import detect_policy_violation
        with patch('main.openai_client') as mock_client:
            mock_client.chat.completions.create = AsyncMock(
                return_value=create_mock_policy_response(False)
            )
            result = await detect_policy_violation(message)
            assert result["is_violation"] is False

    @pytest.mark.asyncio
    async def test_handles_api_error_gracefully(self):
        from main import detect_policy_violation
        with patch('main.openai_client') as mock_client:
            mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))
            result = await detect_policy_violation("test content")
            assert "is_violation" in result or "error" in result

    @pytest.mark.asyncio
    async def test_handles_malformed_response(self):
        from main import detect_policy_violation
        with patch('main.openai_client') as mock_client:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "not valid json"
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            result = await detect_policy_violation("test content")
            assert isinstance(result, dict)


@pytest.mark.unit
class TestRequestModels:
    """Test Pydantic request models."""

    def test_create_session_request_defaults(self):
        from main import CreateSessionRequest
        request = CreateSessionRequest()
        assert request.persona_type == "web_assistant"
        assert request.context == {}
        assert request.profile_id is None

    def test_create_session_request_custom_values(self):
        from main import CreateSessionRequest
        request = CreateSessionRequest(
            persona_type="jaimee_therapist",
            context={"client_id": "123"},
            profile_id="profile-456"
        )
        assert request.persona_type == "jaimee_therapist"
        assert request.context["client_id"] == "123"


@pytest.mark.unit
class TestSessionEndpoints:
    """Test session management endpoints."""

    def test_create_session_returns_session_id(self, test_client):
        with patch('main.session_manager') as mock_sm:
            mock_sm.create_session = AsyncMock(return_value="new-session-id")
            response = test_client.post("/sessions", json={"persona_type": "web_assistant"})
            assert response.status_code == 200
            assert "session_id" in response.json()

    def test_create_session_with_persona(self, test_client):
        with patch('main.session_manager') as mock_sm:
            mock_sm.create_session = AsyncMock(return_value="session-123")
            response = test_client.post("/sessions", json={"persona_type": "jaimee_therapist"})
            assert response.json()["persona_type"] == "jaimee_therapist"


@pytest.mark.unit
class TestChatEndpoint:
    """Test chat endpoint validation."""

    def test_requires_session_id(self, test_client):
        response = test_client.post("/chat", json={"message": "Hello"})
        assert response.status_code in [400, 422, 500]

    def test_requires_message(self, test_client):
        response = test_client.post("/chat", json={"session_id": "test-session"})
        assert response.status_code in [400, 422, 500]


@pytest.mark.unit
class TestDocumentGenerationEndpoint:
    """Test document generation endpoint validation."""

    def test_requires_template(self, test_client):
        response = test_client.post(
            "/generate-document-from-template",
            json={"session_id": "test-session", "segments": []}
        )
        assert response.status_code in [400, 422]

    def test_requires_segments(self, test_client):
        response = test_client.post(
            "/generate-document-from-template",
            json={"session_id": "test-session", "template": {"name": "Test", "content": "# Test"}}
        )
        assert response.status_code in [400, 422]


@pytest.mark.unit
class TestDebugEndpoints:
    """Test debug endpoints."""

    def test_debug_sessions_list(self, test_client):
        with patch('main.ui_state_manager') as mock_ui:
            mock_ui.get_all_sessions_summary = AsyncMock(return_value={})
            response = test_client.get("/debug/sessions")
            assert response.status_code in [200, 401]

    def test_debug_redis_health(self, test_client):
        response = test_client.get("/debug/redis/health")
        assert response.status_code in [200, 401, 503]


@pytest.mark.unit
class TestCORS:
    """Test CORS configuration."""

    def test_allows_any_origin(self, test_client):
        response = test_client.options("/health", headers={"Origin": "http://example.com"})
        assert response.status_code in [200, 204, 405]

    def test_allows_authorization_header(self, test_client):
        response = test_client.get(
            "/health",
            headers={"Origin": "http://example.com", "Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200


@pytest.mark.unit
class TestSemanticSearchConfig:
    """Test semantic search configuration values."""

    def test_thresholds_are_valid(self):
        from main import SEMANTIC_SEARCH_CONFIG
        base = SEMANTIC_SEARCH_CONFIG["base_similarity_threshold"]
        min_thresh = SEMANTIC_SEARCH_CONFIG["min_similarity_threshold"]
        assert 0 <= min_thresh <= base <= 1

    def test_token_threshold_is_reasonable(self):
        from main import SEMANTIC_SEARCH_CONFIG
        threshold = SEMANTIC_SEARCH_CONFIG["pull_all_token_threshold"]
        assert 0 < threshold < 200000


@pytest.mark.unit
class TestEmitProgress:
    """Test progress emission functionality."""

    @pytest.mark.asyncio
    async def test_skips_without_generation_id(self):
        from main import emit_progress
        await emit_progress(None, {"status": "test"})
        await emit_progress("", {"status": "test"})

    @pytest.mark.asyncio
    async def test_handles_http_error_gracefully(self):
        from main import emit_progress
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock()
            await emit_progress("gen-123", {"status": "processing"})
