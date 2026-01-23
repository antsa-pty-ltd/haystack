"""
Pytest configuration and shared fixtures for AI Scribe testing.

This file contains:
- Common test fixtures (mock clients, sample data)
- Golden test datasets
- Helper functions for test assertions
"""

import pytest
import json
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime


# ============================================================================
# GOLDEN TEST DATA - Sample transcripts for testing
# ============================================================================

SAMPLE_TRANSCRIPT_SEGMENTS = [
    {
        "id": "seg-001",
        "transcript_id": "trans-001",
        "speaker": "Speaker 0",
        "text": "How have you been feeling since our last session?",
        "start_time": 0,
        "end_time": 5,
        "confidence": 0.95,
        "sentiment_label": "neutral",
        "sentiment_score": 0.5
    },
    {
        "id": "seg-002",
        "transcript_id": "trans-001",
        "speaker": "Speaker 1",
        "text": "I've been feeling much better. The breathing exercises you taught me have really helped with my anxiety.",
        "start_time": 6,
        "end_time": 15,
        "confidence": 0.92,
        "sentiment_label": "positive",
        "sentiment_score": 0.8
    },
    {
        "id": "seg-003",
        "transcript_id": "trans-001",
        "speaker": "Speaker 0",
        "text": "That's wonderful to hear. Can you tell me more about when you've been using them?",
        "start_time": 16,
        "end_time": 22,
        "confidence": 0.94,
        "sentiment_label": "positive",
        "sentiment_score": 0.7
    },
    {
        "id": "seg-004",
        "transcript_id": "trans-001",
        "speaker": "Speaker 1",
        "text": "I use them mostly in the morning when I wake up feeling stressed, and before important meetings at work.",
        "start_time": 23,
        "end_time": 32,
        "confidence": 0.91,
        "sentiment_label": "neutral",
        "sentiment_score": 0.5
    },
    {
        "id": "seg-005",
        "transcript_id": "trans-001",
        "speaker": "Speaker 0",
        "text": "Let's continue working on those coping strategies. I'd also like to introduce some mindfulness techniques today.",
        "start_time": 33,
        "end_time": 42,
        "confidence": 0.93,
        "sentiment_label": "positive",
        "sentiment_score": 0.6
    }
]

SAMPLE_LONG_TRANSCRIPT_SEGMENTS = SAMPLE_TRANSCRIPT_SEGMENTS * 50  # 250 segments for large session tests

SAMPLE_TEMPLATE_SESSION_NOTES = {
    "id": "template-001",
    "name": "Session Notes",
    "content": """# Session Notes

## Client Information
**Client Name:** {{clientName}}
**Date:** {{date}}

## Subjective
(only include if explicitly mentioned in transcript)
Document what the client reported about their experiences, feelings, and concerns.

## Objective
(only include if explicitly mentioned in transcript)
Document observable behaviors and clinical observations.

## Assessment
(only include if explicitly mentioned in transcript)
Document practitioner's assessment of progress and current status.

## Plan
(only include if explicitly mentioned in transcript)
Document next steps, homework, and treatment plan modifications.

---
**Practitioner:** {{practitionerName}}
""",
    "description": "Standard session notes template",
    "icon": "FileTextOutlined",
    "color": "#4A90E2",
    "tags": ["clinical", "session", "notes"],
    "is_private": False
}

SAMPLE_TEMPLATE_TREATMENT_PLAN = {
    "id": "template-002",
    "name": "Treatment Plan",
    "content": """# Treatment Plan

## Client Information
**Client:** {{clientName}}
**Date:** {{date}}
**Practitioner:** {{practitionerName}}

## Presenting Issues
(only include if explicitly mentioned in transcript)

## Treatment Goals
(only include if explicitly mentioned in transcript)

## Interventions
(only include if explicitly mentioned in transcript)

## Progress Indicators
(only include if explicitly mentioned in transcript)
""",
    "description": "Treatment planning template",
    "icon": "SolutionOutlined",
    "color": "#52C41A",
    "tags": ["clinical", "treatment", "plan"]
}

SAMPLE_CLIENT_INFO = {
    "id": "client-001",
    "name": "Sarah Johnson"
}

SAMPLE_PRACTITIONER_INFO = {
    "id": "practitioner-001",
    "name": "Dr. Michael Chen"
}


# ============================================================================
# POLICY VIOLATION TEST CASES
# ============================================================================

POLICY_VIOLATION_CASES = [
    # Should be FLAGGED (violations)
    {
        "content": "Please diagnose the client with depression based on this session.",
        "should_flag": True,
        "description": "Direct diagnosis request"
    },
    {
        "content": "Determine if this client meets DSM-5 criteria for Major Depressive Disorder.",
        "should_flag": True,
        "description": "DSM criteria request"
    },
    {
        "content": "Assess whether the client has bipolar disorder based on the symptoms described.",
        "should_flag": True,
        "description": "Bipolar assessment request"
    },
    {
        "content": "The client meets criteria for PTSD. Document this diagnosis.",
        "should_flag": True,
        "description": "PTSD diagnosis statement"
    },
    {
        "content": "Prescribe appropriate medication for the client's anxiety.",
        "should_flag": True,
        "description": "Medication prescription request"
    },
    {
        "content": "Provide a clinical diagnosis for this client's mental health condition.",
        "should_flag": True,
        "description": "Generic clinical diagnosis request"
    },
    {
        "content": "Evaluate whether the patient should be diagnosed with generalized anxiety disorder.",
        "should_flag": True,
        "description": "GAD diagnosis evaluation"
    },
    {
        "content": "Based on the ICD-10 criteria, classify this client's disorder.",
        "should_flag": True,
        "description": "ICD-10 classification request"
    },

    # Should be ALLOWED (safe)
    {
        "content": "Document the presenting concerns discussed in this session.",
        "should_flag": False,
        "description": "Presenting concerns documentation"
    },
    {
        "content": "Describe the mood patterns observed during the session.",
        "should_flag": False,
        "description": "Mood pattern observation"
    },
    {
        "content": "Note the symptoms reported by the client.",
        "should_flag": False,
        "description": "Symptom documentation"
    },
    {
        "content": "Suggest coping strategies discussed in the session.",
        "should_flag": False,
        "description": "Coping strategies documentation"
    },
    {
        "content": "Create session notes documenting what was discussed.",
        "should_flag": False,
        "description": "Standard session notes"
    },
    {
        "content": "Document the therapeutic interventions used by the practitioner.",
        "should_flag": False,
        "description": "Intervention documentation"
    },
    {
        "content": "Record the client's self-reported experiences and feelings.",
        "should_flag": False,
        "description": "Self-report documentation"
    },
    {
        "content": "Track treatment progress and goals for the next session.",
        "should_flag": False,
        "description": "Progress tracking"
    },
    {
        "content": """CRITICAL INSTRUCTIONS FOR AI ASSISTANT:
- NEVER provide, suggest, or imply any medical diagnoses
Document session notes below.""",
        "should_flag": False,
        "description": "Template with anti-diagnosis warnings (safety instructions)"
    }
]


# ============================================================================
# PERSONALIZATION TEST CASES
# ============================================================================

PERSONALIZATION_FORBIDDEN_TERMS = [
    "the client",
    "the patient",
    "the therapist",
    "the practitioner",
    "the counselor",
    "the individual",
    "client",  # when used alone as reference
    "patient",  # when used alone as reference
]

PERSONALIZATION_TEST_CASES = [
    {
        "client_name": "Sarah Johnson",
        "practitioner_name": "Dr. Michael Chen",
        "must_contain": ["Sarah Johnson", "Dr. Michael Chen"],
        "must_not_contain": PERSONALIZATION_FORBIDDEN_TERMS
    },
    {
        "client_name": "Jose O'Brien-Smith",
        "practitioner_name": "Dr. Maria Garcia-Lopez",
        "must_contain": ["Jose O'Brien-Smith", "Dr. Maria Garcia-Lopez"],
        "must_not_contain": PERSONALIZATION_FORBIDDEN_TERMS
    },
    {
        "client_name": "Jean-Pierre Dubois",
        "practitioner_name": "Dr. Emily Watson",
        "must_contain": ["Jean-Pierre Dubois", "Dr. Emily Watson"],
        "must_not_contain": PERSONALIZATION_FORBIDDEN_TERMS
    }
]


# ============================================================================
# VARIABLE SUBSTITUTION TEST CASES
# ============================================================================

VARIABLE_SUBSTITUTION_CASES = [
    {
        "template": "Dear {{clientName}},\nSigned, {{practitionerName}}",
        "variables": {"clientName": "John Smith", "practitionerName": "Dr. Jane Doe"},
        "expected_contains": ["John Smith", "Dr. Jane Doe"],
        "expected_not_contains": ["{{clientName}}", "{{practitionerName}}"]
    },
    {
        "template": "Session date: {{date}}",
        "variables": {"date": "January 15, 2026"},
        "expected_contains": ["January 15, 2026"],
        "expected_not_contains": ["{{date}}"]
    },
    {
        "template": "Provider: {{providerNumber}}",
        "variables": {"providerNumber": "PRV-12345"},
        "expected_contains": ["PRV-12345"],
        "expected_not_contains": ["{{providerNumber}}"]
    }
]


# ============================================================================
# EDGE CASE TEST DATA
# ============================================================================

EDGE_CASES = {
    "empty_transcript": {
        "segments": [],
        "description": "Empty transcript with no segments"
    },
    "very_long_transcript": {
        "segments": SAMPLE_LONG_TRANSCRIPT_SEGMENTS,
        "description": "Very long transcript exceeding normal limits"
    },
    "special_characters_name": {
        "client_name": "Jose O'Brien-Smith",
        "practitioner_name": "Dr. Maria Garcia-Lopez",
        "description": "Names with special characters"
    },
    "unicode_content": {
        "segments": [
            {
                "id": "seg-unicode",
                "transcript_id": "trans-unicode",
                "speaker": "Speaker 1",
                "text": "I've been feeling really down lately...",
                "start_time": 0,
                "end_time": 5,
                "confidence": 0.9,
                "sentiment_label": "negative",
                "sentiment_score": 0.3
            }
        ],
        "description": "Content with unicode characters"
    },
    "multiple_speakers": {
        "segments": [
            {"speaker": "Speaker 0", "text": "Hello", "start_time": 0},
            {"speaker": "Speaker 1", "text": "Hi there", "start_time": 2},
            {"speaker": "Unknown", "text": "[unclear]", "start_time": 4},
            {"speaker": "Speaker 2", "text": "Third person", "start_time": 6}
        ],
        "description": "Multiple speakers including unknown"
    }
}


# ============================================================================
# PYTEST FIXTURES
# ============================================================================

@pytest.fixture
def sample_segments():
    """Return sample transcript segments for testing."""
    return SAMPLE_TRANSCRIPT_SEGMENTS.copy()


@pytest.fixture
def sample_long_segments():
    """Return long transcript segments for testing token limits."""
    return SAMPLE_LONG_TRANSCRIPT_SEGMENTS.copy()


@pytest.fixture
def sample_template():
    """Return sample session notes template."""
    return SAMPLE_TEMPLATE_SESSION_NOTES.copy()


@pytest.fixture
def sample_treatment_plan_template():
    """Return sample treatment plan template."""
    return SAMPLE_TEMPLATE_TREATMENT_PLAN.copy()


@pytest.fixture
def sample_client_info():
    """Return sample client info."""
    return SAMPLE_CLIENT_INFO.copy()


@pytest.fixture
def sample_practitioner_info():
    """Return sample practitioner info."""
    return SAMPLE_PRACTITIONER_INFO.copy()


@pytest.fixture
def mock_openai_client():
    """Create a mock OpenAI client for testing."""
    mock_client = AsyncMock()

    # Mock the chat completions response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = """# Session Notes

## Client Information
**Client Name:** Sarah Johnson
**Date:** January 16, 2026

## Subjective
Sarah Johnson reported feeling much better since the last session. Sarah Johnson mentioned that the breathing exercises have been helpful for managing anxiety.

## Objective
Sarah Johnson appeared calm and engaged during the session. Sarah Johnson demonstrated good insight into her progress.

## Assessment
Dr. Michael Chen notes that Sarah Johnson has made significant progress with anxiety management techniques.

## Plan
Continue with breathing exercises. Dr. Michael Chen will introduce mindfulness techniques in the next session.

---
**Practitioner:** Dr. Michael Chen
"""
    mock_response.choices[0].finish_reason = "stop"
    mock_response.usage = MagicMock()
    mock_response.usage.total_tokens = 500

    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    return mock_client


@pytest.fixture
def mock_openai_client_policy_check():
    """Create a mock OpenAI client for policy violation detection testing."""
    mock_client = AsyncMock()

    async def mock_create(**kwargs):
        """Simulate policy check based on content."""
        messages = kwargs.get("messages", [])
        user_message = next((m["content"] for m in messages if m["role"] == "user"), "")

        # Check for violation keywords
        violation_keywords = [
            "diagnose", "diagnosis", "DSM", "ICD", "meets criteria",
            "prescribe", "medication", "bipolar", "depression disorder",
            "anxiety disorder", "PTSD diagnosis"
        ]

        is_violation = any(kw.lower() in user_message.lower() for kw in violation_keywords)

        # Also check for safe patterns that should NOT be flagged
        safe_patterns = [
            "CRITICAL INSTRUCTIONS FOR AI ASSISTANT",
            "NEVER provide, suggest, or imply any medical diagnoses",
            "presenting concerns",
            "reported symptoms",
            "coping strategies"
        ]

        # If it contains safety instructions, it's not a violation
        if any(pattern in user_message for pattern in safe_patterns):
            is_violation = False

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "is_violation": is_violation,
            "violation_type": "medical_diagnosis_request" if is_violation else None,
            "reason": "Template requests medical diagnosis" if is_violation else None,
            "confidence": "high"
        })

        return mock_response

    mock_client.chat.completions.create = mock_create
    return mock_client


@pytest.fixture
def policy_violation_cases():
    """Return policy violation test cases."""
    return POLICY_VIOLATION_CASES.copy()


@pytest.fixture
def personalization_test_cases():
    """Return personalization test cases."""
    return PERSONALIZATION_TEST_CASES.copy()


@pytest.fixture
def variable_substitution_cases():
    """Return variable substitution test cases."""
    return VARIABLE_SUBSTITUTION_CASES.copy()


@pytest.fixture
def edge_cases():
    """Return edge case test data."""
    return EDGE_CASES.copy()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def check_personalization(document: str, client_name: str, practitioner_name: str) -> Dict[str, Any]:
    """
    Check if a generated document properly uses personalized names.

    Returns:
        Dict with 'passed', 'issues' keys
    """
    import re
    issues = []
    document_lower = document.lower()

    # Only check for multi-word forbidden terms that are clearly generic references
    # Single words like "client" can be part of labels like "Client Name:" or "Client Information"
    multi_word_forbidden = [
        "the client",
        "the patient",
        "the therapist",
        "the practitioner",
        "the counselor",
        "the individual",
    ]

    for term in multi_word_forbidden:
        # Use word boundary matching to avoid false positives
        pattern = r'\b' + re.escape(term) + r'\b'
        matches = list(re.finditer(pattern, document_lower))

        if matches:
            # Filter out matches that are part of labels (followed by colon or within **)
            real_matches = []
            for match in matches:
                pos = match.start()
                # Check context - is this in a label?
                before = document_lower[max(0, pos-5):pos]
                after = document_lower[match.end():match.end()+5]

                # Skip if it's part of a markdown header or label
                if "**" in before or ":" in after[:3] or "#" in before:
                    continue
                real_matches.append(pos)

            if real_matches:
                issues.append(f"Found forbidden term '{term}' at positions: {real_matches[:3]}")

    # Check that actual names are used
    if client_name.lower() not in document_lower:
        issues.append(f"Client name '{client_name}' not found in document")

    if practitioner_name.lower() not in document_lower:
        issues.append(f"Practitioner name '{practitioner_name}' not found in document")

    return {
        "passed": len(issues) == 0,
        "issues": issues
    }


def check_no_diagnosis(document: str) -> Dict[str, Any]:
    """
    Check that a document doesn't contain diagnostic language.

    Returns:
        Dict with 'passed', 'issues' keys
    """
    import re

    diagnosis_patterns = [
        r"diagnosed with",
        r"diagnosis of",
        r"meets criteria for",
        r"suffers from",
        r"has (depression|anxiety|PTSD|bipolar|schizophrenia)",
        r"DSM-[IV5]",
        r"ICD-\d+",
        r"clinical diagnosis",
        r"psychiatric diagnosis"
    ]

    issues = []
    document_lower = document.lower()

    for pattern in diagnosis_patterns:
        matches = re.findall(pattern, document_lower, re.IGNORECASE)
        if matches:
            issues.append(f"Found diagnosis pattern '{pattern}': {matches[:3]}")

    return {
        "passed": len(issues) == 0,
        "issues": issues
    }


def check_template_sections(document: str, expected_sections: List[str]) -> Dict[str, Any]:
    """
    Check that a document contains expected template sections.

    Returns:
        Dict with 'passed', 'missing_sections', 'found_sections' keys
    """
    found = []
    missing = []

    for section in expected_sections:
        if section.lower() in document.lower():
            found.append(section)
        else:
            missing.append(section)

    return {
        "passed": len(missing) == 0,
        "found_sections": found,
        "missing_sections": missing
    }


def check_variable_substitution(document: str, expected_not_present: List[str]) -> Dict[str, Any]:
    """
    Check that template variables have been substituted.

    Returns:
        Dict with 'passed', 'unsubstituted' keys
    """
    unsubstituted = []

    for var in expected_not_present:
        if var in document:
            unsubstituted.append(var)

    return {
        "passed": len(unsubstituted) == 0,
        "unsubstituted": unsubstituted
    }


# ============================================================================
# UI STATE MANAGER FIXTURES
# ============================================================================

@pytest.fixture
def sample_ui_state():
    """Sample UI state for testing."""
    return {
        "session_id": "test-session-123",
        "last_updated": "2026-01-23T10:00:00Z",
        "page_type": "transcribe_page",
        "page_url": "/transcribe",
        "loadedSessions": [
            {
                "sessionId": "sess-001",
                "clientId": "client-001",
                "clientName": "John Doe",
                "content": "Session content here",
                "metadata": {"duration": 3600}
            }
        ],
        "currentClient": {
            "clientId": "client-001",
            "clientName": "John Doe"
        },
        "selectedTemplate": {
            "templateId": "template-001",
            "templateName": "Session Notes",
            "templateContent": "# Session Notes\n...",
            "templateDescription": "Standard notes"
        },
        "generatedDocuments": [],
        "sessionCount": 1,
        "documentCount": 0,
        "client_id": "client-001",
        "client_name": "John Doe",
        "active_tab": "transcribe",
        "profile_id": "profile-001"
    }


# ============================================================================
# MOCK REDIS FIXTURES
# ============================================================================

@pytest.fixture
def mock_redis_client():
    """Create a mock Redis async client."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.setex = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.keys = AsyncMock(return_value=[])
    mock.ping = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_redis_sync_client():
    """Create a mock Redis sync client."""
    mock = MagicMock()
    mock.get = MagicMock(return_value=None)
    mock.setex = MagicMock(return_value=True)
    mock.delete = MagicMock(return_value=1)
    mock.keys = MagicMock(return_value=[])
    mock.ping = MagicMock(return_value=True)
    return mock


# ============================================================================
# SETTINGS FIXTURES
# ============================================================================

@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    mock = MagicMock()
    mock.openai_api_key = "sk-test-key-for-testing"
    mock.redis_url = "redis://localhost:6379"
    mock.nestjs_api_url = "http://localhost:8080"
    mock.log_level = "INFO"
    mock.max_requests_per_user = 10
    mock.session_timeout_minutes = 240
    mock.show_tool_banner = True
    mock.show_raw_tool_json = False
    mock.max_concurrent_requests = 10000
    mock.host = "0.0.0.0"
    mock.port = 8001
    return mock


# ============================================================================
# API RESPONSE FIXTURES
# ============================================================================

@pytest.fixture
def mock_nestjs_api_response():
    """Mock response from NestJS API."""
    return {
        "success": True,
        "data": {
            "clients": [
                {"id": "client-001", "name": "John Doe"},
                {"id": "client-002", "name": "Jane Smith"}
            ]
        }
    }


@pytest.fixture
def mock_session_segments():
    """Mock session segments from API."""
    return [
        {
            "id": "seg-001",
            "text": "How have you been feeling?",
            "speaker": "Speaker 0",
            "start_time": 0,
            "end_time": 5
        },
        {
            "id": "seg-002",
            "text": "I've been feeling better lately.",
            "speaker": "Speaker 1",
            "start_time": 6,
            "end_time": 12
        }
    ]
