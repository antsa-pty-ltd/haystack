"""
RAGAS-based quality evaluation tests for document generation.

These tests use the RAGAS framework with REAL OpenAI API calls to evaluate:
- Faithfulness: Is the generated document grounded in the transcript segments?
- Response Relevancy: Does the document address the template requirements?
- Context Precision: Are the retrieved/used segments relevant?

Tests marked with @pytest.mark.quality use real API calls and incur costs.

Run with: pytest tests/quality/test_ragas_document_quality.py -v -m quality
"""

import pytest
import os
import asyncio
from typing import Dict, Any, List
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# RAGAS imports (using new API to avoid deprecation warnings)
from ragas.metrics._faithfulness import Faithfulness
from ragas.metrics._answer_relevance import ResponseRelevancy
from ragas.metrics._context_precision import LLMContextPrecisionWithoutReference
from ragas.dataset_schema import SingleTurnSample
from ragas.llms import llm_factory

# OpenAI for document generation
from openai import OpenAI, AsyncOpenAI

# Import the document generation function
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from document_generation.generator import generate_document_from_context


# ============================================================================
# TEST DATA - Comprehensive session segments for evaluation
# ============================================================================

THERAPY_SESSION_SEGMENTS = [
    {
        "id": "seg-001",
        "transcript_id": "trans-001",
        "speaker": "Therapist",
        "text": "How have you been feeling since our last session, Sarah?",
        "start_time": 0,
        "end_time": 5,
    },
    {
        "id": "seg-002",
        "transcript_id": "trans-001",
        "speaker": "Client",
        "text": "I've been feeling much better. The breathing exercises you taught me have really helped with my anxiety, especially in the mornings.",
        "start_time": 6,
        "end_time": 18,
    },
    {
        "id": "seg-003",
        "transcript_id": "trans-001",
        "speaker": "Therapist",
        "text": "That's wonderful to hear. Can you tell me more about when you've been using the breathing techniques?",
        "start_time": 19,
        "end_time": 27,
    },
    {
        "id": "seg-004",
        "transcript_id": "trans-001",
        "speaker": "Client",
        "text": "I use them mostly when I wake up feeling stressed, and also before important meetings at work. It helps me stay calm and focused.",
        "start_time": 28,
        "end_time": 42,
    },
    {
        "id": "seg-005",
        "transcript_id": "trans-001",
        "speaker": "Therapist",
        "text": "Excellent. Let's continue working on those coping strategies. Today I'd like to introduce some mindfulness techniques that can complement the breathing exercises.",
        "start_time": 43,
        "end_time": 58,
    },
    {
        "id": "seg-006",
        "transcript_id": "trans-001",
        "speaker": "Client",
        "text": "I'm interested in learning more about mindfulness. I've heard it can help with anxiety.",
        "start_time": 59,
        "end_time": 68,
    },
    {
        "id": "seg-007",
        "transcript_id": "trans-001",
        "speaker": "Therapist",
        "text": "Absolutely. Mindfulness is about being present in the moment without judgment. Let's start with a simple body scan exercise.",
        "start_time": 69,
        "end_time": 82,
    },
    {
        "id": "seg-008",
        "transcript_id": "trans-001",
        "speaker": "Therapist",
        "text": "For homework this week, I'd like you to practice the breathing exercises twice daily and try the body scan once before bed.",
        "start_time": 300,
        "end_time": 315,
    },
]

TREATMENT_PLAN_SEGMENTS = [
    {
        "id": "tp-001",
        "transcript_id": "trans-002",
        "speaker": "Therapist",
        "text": "Today we'll discuss your treatment goals for the coming weeks, John.",
        "start_time": 0,
        "end_time": 8,
    },
    {
        "id": "tp-002",
        "transcript_id": "trans-002",
        "speaker": "Client",
        "text": "I'd really like to focus on managing my sleep issues and reducing my overall anxiety levels.",
        "start_time": 9,
        "end_time": 20,
    },
    {
        "id": "tp-003",
        "transcript_id": "trans-002",
        "speaker": "Therapist",
        "text": "Those are excellent goals. For sleep, we can work on sleep hygiene techniques like maintaining a consistent bedtime routine.",
        "start_time": 21,
        "end_time": 35,
    },
    {
        "id": "tp-004",
        "transcript_id": "trans-002",
        "speaker": "Client",
        "text": "That sounds helpful. What about the anxiety?",
        "start_time": 36,
        "end_time": 42,
    },
    {
        "id": "tp-005",
        "transcript_id": "trans-002",
        "speaker": "Therapist",
        "text": "For anxiety, we'll continue with CBT techniques and add progressive muscle relaxation to your toolkit.",
        "start_time": 43,
        "end_time": 55,
    },
    {
        "id": "tp-006",
        "transcript_id": "trans-002",
        "speaker": "Therapist",
        "text": "I'll also assign some journaling exercises as homework between our sessions to track your anxiety triggers.",
        "start_time": 56,
        "end_time": 68,
    },
]

SESSION_NOTES_TEMPLATE = {
    "id": "template-session-notes",
    "name": "Session Notes (SOAP Format)",
    "content": """# Session Notes

## Client Information
**Client Name:** {{clientName}}
**Date:** {{date}}

## Subjective
Document what the client reported about their experiences, feelings, and concerns during this session.

## Objective
Document observable behaviors and clinical observations made during the session.

## Assessment
Document the practitioner's assessment of progress and current status.

## Plan
Document next steps, homework assignments, and any treatment plan modifications.

---
**Practitioner:** {{practitionerName}}
"""
}

TREATMENT_PLAN_TEMPLATE = {
    "id": "template-treatment-plan",
    "name": "Treatment Plan",
    "content": """# Treatment Plan

## Client Information
**Client:** {{clientName}}
**Date:** {{date}}
**Practitioner:** {{practitionerName}}

## Presenting Issues
Document the primary concerns and issues identified.

## Treatment Goals
List the specific, measurable treatment goals discussed.

## Interventions
Document the therapeutic interventions and techniques to be used.

## Progress Indicators
Describe how progress will be measured.

## Homework/Between-Session Activities
List any assignments given to the client.
"""
}


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def openai_client():
    """Create real OpenAI client for document generation."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY environment variable not set")
    return AsyncOpenAI(api_key=api_key)


@pytest.fixture
def ragas_llm():
    """Create LLM wrapper for RAGAS evaluation."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY environment variable not set")

    # Use GPT-4o-mini for evaluation (faster and more cost effective)
    # with higher max_tokens to handle longer documents
    client = OpenAI(api_key=api_key)
    return llm_factory("gpt-4o-mini", client=client, run_config={"max_tokens": 8000})


@pytest.fixture
def faithfulness_metric(ragas_llm):
    """Create Faithfulness metric with LLM."""
    metric = Faithfulness(llm=ragas_llm)
    return metric


@pytest.fixture
def relevancy_metric(ragas_llm):
    """Create Response Relevancy metric with LLM."""
    metric = ResponseRelevancy(llm=ragas_llm)
    return metric


@pytest.fixture
def context_precision_metric(ragas_llm):
    """Create Context Precision metric with LLM."""
    metric = LLMContextPrecisionWithoutReference(llm=ragas_llm)
    return metric


@pytest.fixture
def therapy_session_segments():
    """Return therapy session segments."""
    return THERAPY_SESSION_SEGMENTS.copy()


@pytest.fixture
def treatment_plan_segments():
    """Return treatment plan segments."""
    return TREATMENT_PLAN_SEGMENTS.copy()


@pytest.fixture
def session_notes_template():
    """Return session notes template."""
    return SESSION_NOTES_TEMPLATE.copy()


@pytest.fixture
def treatment_plan_template():
    """Return treatment plan template."""
    return TREATMENT_PLAN_TEMPLATE.copy()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def generate_document_for_test(
    segments: List[Dict],
    template: Dict,
    client_name: str,
    practitioner_name: str,
    openai_client: AsyncOpenAI
) -> Dict[str, Any]:
    """Generate a document using real OpenAI API."""
    return await generate_document_from_context(
        segments=segments,
        template=template,
        client_info={"id": "test-client", "name": client_name},
        practitioner_info={"id": "test-practitioner", "name": practitioner_name},
        generation_instructions=None,
        openai_client=openai_client,
    )


def create_ragas_sample(
    user_query: str,
    response: str,
    contexts: List[str]
) -> SingleTurnSample:
    """Create a RAGAS SingleTurnSample for evaluation."""
    return SingleTurnSample(
        user_input=user_query,
        response=response,
        retrieved_contexts=contexts
    )


# ============================================================================
# FAITHFULNESS TESTS
# ============================================================================

@pytest.mark.quality
@pytest.mark.asyncio
class TestDocumentFaithfulness:
    """Test that generated documents are faithful to transcript content."""

    async def test_session_notes_faithfulness(
        self,
        openai_client,
        faithfulness_metric,
        therapy_session_segments,
        session_notes_template
    ):
        """
        Test that session notes are grounded in the actual transcript content.

        Faithfulness measures whether the document makes claims that are
        supported by the source transcript segments.
        """
        # Generate document using real API
        document = await generate_document_for_test(
            segments=therapy_session_segments,
            template=session_notes_template,
            client_name="Sarah Johnson",
            practitioner_name="Dr. Michael Chen",
            openai_client=openai_client
        )

        # Extract contexts from segments
        contexts = [seg["text"] for seg in therapy_session_segments]

        # Create RAGAS sample
        sample = create_ragas_sample(
            user_query=f"Generate session notes using this template: {session_notes_template['content']}",
            response=document["content"],
            contexts=contexts
        )

        # Evaluate faithfulness
        score = await faithfulness_metric.single_turn_ascore(sample)

        print(f"\n=== Faithfulness Test Results ===")
        print(f"Score: {score:.3f}")
        print(f"Document length: {len(document['content'])} chars")
        print(f"Segments used: {len(therapy_session_segments)}")

        # Threshold: 0.8 for clinical documentation (must be highly faithful)
        assert score >= 0.8, f"Faithfulness score {score:.3f} below 0.8 threshold"

    async def test_treatment_plan_faithfulness(
        self,
        openai_client,
        faithfulness_metric,
        treatment_plan_segments,
        treatment_plan_template
    ):
        """
        Test that treatment plans are faithful to session content.
        """
        document = await generate_document_for_test(
            segments=treatment_plan_segments,
            template=treatment_plan_template,
            client_name="John Smith",
            practitioner_name="Dr. Emily Watson",
            openai_client=openai_client
        )

        contexts = [seg["text"] for seg in treatment_plan_segments]

        sample = create_ragas_sample(
            user_query=f"Generate treatment plan using template: {treatment_plan_template['content']}",
            response=document["content"],
            contexts=contexts
        )

        score = await faithfulness_metric.single_turn_ascore(sample)

        print(f"\n=== Treatment Plan Faithfulness ===")
        print(f"Score: {score:.3f}")

        assert score >= 0.8, f"Faithfulness score {score:.3f} below threshold"

    async def test_no_hallucinated_interventions(
        self,
        openai_client,
        faithfulness_metric,
        therapy_session_segments,
        session_notes_template
    ):
        """
        Test that documents don't include interventions not discussed.

        This is critical for clinical documentation - we cannot invent
        therapeutic interventions that weren't actually discussed.
        """
        document = await generate_document_for_test(
            segments=therapy_session_segments,
            template=session_notes_template,
            client_name="Sarah Johnson",
            practitioner_name="Dr. Michael Chen",
            openai_client=openai_client
        )

        content_lower = document["content"].lower()

        # These interventions were NOT discussed in the segments
        hallucinated_interventions = [
            "emdr",
            "exposure therapy",
            "dialectical behavior therapy",
            "medication adjustment",
            "group therapy",
            "hypnotherapy",
        ]

        hallucinations_found = []
        for intervention in hallucinated_interventions:
            if intervention in content_lower:
                hallucinations_found.append(intervention)

        print(f"\n=== Hallucination Check ===")
        print(f"Hallucinations found: {hallucinations_found}")

        assert len(hallucinations_found) == 0, \
            f"Document contains hallucinated interventions: {hallucinations_found}"


# ============================================================================
# RESPONSE RELEVANCY TESTS
# ============================================================================

@pytest.mark.quality
@pytest.mark.asyncio
class TestDocumentRelevancy:
    """Test that generated documents are relevant to template requirements."""

    async def test_session_notes_relevancy(
        self,
        openai_client,
        relevancy_metric,
        therapy_session_segments,
        session_notes_template
    ):
        """
        Test that session notes address all template sections.
        """
        document = await generate_document_for_test(
            segments=therapy_session_segments,
            template=session_notes_template,
            client_name="Sarah Johnson",
            practitioner_name="Dr. Michael Chen",
            openai_client=openai_client
        )

        contexts = [seg["text"] for seg in therapy_session_segments]

        sample = create_ragas_sample(
            user_query="Generate comprehensive session notes covering subjective reports, objective observations, assessment, and treatment plan",
            response=document["content"],
            contexts=contexts
        )

        score = await relevancy_metric.single_turn_ascore(sample)

        print(f"\n=== Relevancy Test Results ===")
        print(f"Score: {score:.3f}")

        # Threshold: 0.7 for relevancy (some flexibility in how template is filled)
        assert score >= 0.7, f"Relevancy score {score:.3f} below 0.7 threshold"

    async def test_template_sections_covered(
        self,
        openai_client,
        therapy_session_segments,
        session_notes_template
    ):
        """
        Test that all expected SOAP sections are present in the document.
        """
        document = await generate_document_for_test(
            segments=therapy_session_segments,
            template=session_notes_template,
            client_name="Sarah Johnson",
            practitioner_name="Dr. Michael Chen",
            openai_client=openai_client
        )

        content = document["content"].lower()

        # SOAP format sections
        required_sections = ["subjective", "objective", "assessment", "plan"]
        missing_sections = []

        for section in required_sections:
            if section not in content:
                missing_sections.append(section)

        print(f"\n=== Section Coverage ===")
        print(f"Missing sections: {missing_sections}")

        assert len(missing_sections) == 0, \
            f"Document missing required sections: {missing_sections}"


# ============================================================================
# CONTEXT PRECISION TESTS
# ============================================================================

@pytest.mark.quality
@pytest.mark.asyncio
class TestContextPrecision:
    """Test that the right segments are used for document generation."""

    async def test_therapy_interventions_captured(
        self,
        openai_client,
        therapy_session_segments,
        session_notes_template
    ):
        """
        Test that key therapeutic interventions are captured in the document.
        """
        document = await generate_document_for_test(
            segments=therapy_session_segments,
            template=session_notes_template,
            client_name="Sarah Johnson",
            practitioner_name="Dr. Michael Chen",
            openai_client=openai_client
        )

        content_lower = document["content"].lower()

        # Key interventions that SHOULD be captured (from the segments)
        expected_interventions = [
            "breathing",  # breathing exercises
            "mindfulness",
            "body scan",
        ]

        captured = []
        for intervention in expected_interventions:
            if intervention in content_lower:
                captured.append(intervention)

        coverage = len(captured) / len(expected_interventions)

        print(f"\n=== Intervention Coverage ===")
        print(f"Expected: {expected_interventions}")
        print(f"Captured: {captured}")
        print(f"Coverage: {coverage:.1%}")

        # At least 80% of interventions should be captured
        assert coverage >= 0.8, \
            f"Only {coverage:.1%} of interventions captured, expected >= 80%"

    async def test_homework_assignments_captured(
        self,
        openai_client,
        therapy_session_segments,
        session_notes_template
    ):
        """
        Test that homework assignments are captured in the document.
        """
        document = await generate_document_for_test(
            segments=therapy_session_segments,
            template=session_notes_template,
            client_name="Sarah Johnson",
            practitioner_name="Dr. Michael Chen",
            openai_client=openai_client
        )

        content_lower = document["content"].lower()

        # Homework mentioned in segments: breathing exercises twice daily, body scan before bed
        homework_elements = [
            "breathing",
            "body scan",
            "homework" or "assignment",
        ]

        captured_homework = sum(1 for elem in homework_elements if elem in content_lower)

        print(f"\n=== Homework Capture ===")
        print(f"Elements captured: {captured_homework}/{len(homework_elements)}")

        # At least 2 homework elements should be mentioned
        assert captured_homework >= 2, \
            f"Only {captured_homework} homework elements captured"


# ============================================================================
# PERSONALIZATION TESTS
# ============================================================================

@pytest.mark.quality
@pytest.mark.asyncio
class TestDocumentPersonalization:
    """Test that documents use correct client/practitioner names."""

    async def test_client_name_used(
        self,
        openai_client,
        therapy_session_segments,
        session_notes_template
    ):
        """
        Test that the client's name is used throughout the document.
        """
        client_name = "Sarah Johnson"

        document = await generate_document_for_test(
            segments=therapy_session_segments,
            template=session_notes_template,
            client_name=client_name,
            practitioner_name="Dr. Michael Chen",
            openai_client=openai_client
        )

        content = document["content"]
        content_lower = content.lower()

        # Client name should appear multiple times
        name_count = content_lower.count(client_name.lower())

        # Should NOT use generic terms
        generic_terms = ["the client", "the patient"]
        generic_found = [term for term in generic_terms if term in content_lower]

        print(f"\n=== Personalization Check ===")
        print(f"Client name '{client_name}' count: {name_count}")
        print(f"Generic terms found: {generic_found}")

        assert name_count >= 3, f"Client name only used {name_count} times"
        assert len(generic_found) == 0, f"Generic terms found: {generic_found}"

    async def test_practitioner_name_used(
        self,
        openai_client,
        therapy_session_segments,
        session_notes_template
    ):
        """
        Test that the practitioner's name is used in the document.
        """
        practitioner_name = "Dr. Michael Chen"

        document = await generate_document_for_test(
            segments=therapy_session_segments,
            template=session_notes_template,
            client_name="Sarah Johnson",
            practitioner_name=practitioner_name,
            openai_client=openai_client
        )

        content_lower = document["content"].lower()

        # Practitioner name should appear
        name_count = content_lower.count(practitioner_name.lower())

        # Should NOT use generic terms
        generic_terms = ["the therapist", "the practitioner", "the counselor"]
        generic_found = [term for term in generic_terms if term in content_lower]

        print(f"\n=== Practitioner Name Check ===")
        print(f"Name '{practitioner_name}' count: {name_count}")
        print(f"Generic terms found: {generic_found}")

        assert name_count >= 1, f"Practitioner name not found in document"
        assert len(generic_found) == 0, f"Generic terms found: {generic_found}"


# ============================================================================
# SAFETY COMPLIANCE TESTS
# ============================================================================

@pytest.mark.quality
@pytest.mark.asyncio
class TestDocumentSafetyCompliance:
    """Test that documents comply with safety requirements."""

    async def test_no_diagnosis_in_document(
        self,
        openai_client,
        therapy_session_segments,
        session_notes_template
    ):
        """
        Test that generated documents do NOT contain diagnostic language.

        This is CRITICAL for mental health documentation.
        """
        document = await generate_document_for_test(
            segments=therapy_session_segments,
            template=session_notes_template,
            client_name="Sarah Johnson",
            practitioner_name="Dr. Michael Chen",
            openai_client=openai_client
        )

        content_lower = document["content"].lower()

        # Diagnostic patterns that should NEVER appear
        diagnostic_patterns = [
            "diagnosed with",
            "diagnosis of",
            "meets criteria for",
            "suffers from depression",
            "suffers from anxiety disorder",
            "has bipolar",
            "has ptsd",
            "dsm-5",
            "dsm-iv",
            "icd-10",
            "clinical diagnosis",
        ]

        found_patterns = []
        for pattern in diagnostic_patterns:
            if pattern in content_lower:
                found_patterns.append(pattern)

        print(f"\n=== Diagnosis Check ===")
        print(f"Diagnostic patterns found: {found_patterns}")

        assert len(found_patterns) == 0, \
            f"Document contains diagnostic language: {found_patterns}"

    async def test_no_medication_prescriptions(
        self,
        openai_client,
        therapy_session_segments,
        session_notes_template
    ):
        """
        Test that documents don't prescribe medications.
        """
        document = await generate_document_for_test(
            segments=therapy_session_segments,
            template=session_notes_template,
            client_name="Sarah Johnson",
            practitioner_name="Dr. Michael Chen",
            openai_client=openai_client
        )

        content_lower = document["content"].lower()

        # Prescription patterns
        prescription_patterns = [
            "prescribe",
            "prescribed medication",
            "increase dosage",
            "decrease dosage",
            "start taking",
            "stop taking",
            "mg daily",  # specific dosages
        ]

        found_patterns = []
        for pattern in prescription_patterns:
            if pattern in content_lower:
                found_patterns.append(pattern)

        print(f"\n=== Prescription Check ===")
        print(f"Prescription patterns found: {found_patterns}")

        # Allow some flexibility - "prescribe" might appear in context
        # But should not have specific dosages
        critical_patterns = ["mg daily", "increase dosage", "decrease dosage"]
        critical_found = [p for p in found_patterns if p in critical_patterns]

        assert len(critical_found) == 0, \
            f"Document contains medication prescriptions: {critical_found}"


# ============================================================================
# COMBINED EVALUATION TEST
# ============================================================================

@pytest.mark.quality
@pytest.mark.asyncio
class TestComprehensiveDocumentEvaluation:
    """Run comprehensive RAGAS evaluation on document generation."""

    async def test_full_document_evaluation(
        self,
        openai_client,
        faithfulness_metric,
        relevancy_metric,
        therapy_session_segments,
        session_notes_template
    ):
        """
        Run full RAGAS evaluation with multiple metrics.

        This test provides a comprehensive quality score for document generation.
        """
        # Generate document
        document = await generate_document_for_test(
            segments=therapy_session_segments,
            template=session_notes_template,
            client_name="Sarah Johnson",
            practitioner_name="Dr. Michael Chen",
            openai_client=openai_client
        )

        contexts = [seg["text"] for seg in therapy_session_segments]

        sample = create_ragas_sample(
            user_query="Generate comprehensive clinical session notes",
            response=document["content"],
            contexts=contexts
        )

        # Evaluate with multiple metrics
        faithfulness_score = await faithfulness_metric.single_turn_ascore(sample)
        relevancy_score = await relevancy_metric.single_turn_ascore(sample)

        # Calculate combined score
        combined_score = (faithfulness_score + relevancy_score) / 2

        print("\n" + "=" * 60)
        print("COMPREHENSIVE DOCUMENT EVALUATION RESULTS")
        print("=" * 60)
        print(f"Faithfulness Score: {faithfulness_score:.3f}")
        print(f"Relevancy Score:    {relevancy_score:.3f}")
        print(f"Combined Score:     {combined_score:.3f}")
        print("-" * 60)
        print(f"Document Length:    {len(document['content'])} characters")
        print(f"Word Count:         {document['metadata'].get('wordCount', 'N/A')}")
        print(f"Segments Used:      {len(therapy_session_segments)}")
        print("=" * 60)

        # Thresholds
        assert faithfulness_score >= 0.8, \
            f"Faithfulness {faithfulness_score:.3f} below 0.8 threshold"
        assert relevancy_score >= 0.7, \
            f"Relevancy {relevancy_score:.3f} below 0.7 threshold"
        assert combined_score >= 0.75, \
            f"Combined score {combined_score:.3f} below 0.75 threshold"


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

@pytest.mark.quality
@pytest.mark.asyncio
class TestEdgeCases:
    """Test document generation with edge cases."""

    async def test_short_session_faithfulness(
        self,
        openai_client,
        faithfulness_metric,
        session_notes_template
    ):
        """
        Test faithfulness with minimal transcript content.
        """
        # Very short session - only 2 segments
        short_segments = [
            {
                "id": "short-001",
                "transcript_id": "trans-short",
                "speaker": "Therapist",
                "text": "How are you feeling today, Alex?",
                "start_time": 0,
                "end_time": 4,
            },
            {
                "id": "short-002",
                "transcript_id": "trans-short",
                "speaker": "Client",
                "text": "I'm feeling okay. The anxiety has been better this week.",
                "start_time": 5,
                "end_time": 12,
            },
        ]

        document = await generate_document_for_test(
            segments=short_segments,
            template=session_notes_template,
            client_name="Alex Thompson",
            practitioner_name="Dr. Lisa Park",
            openai_client=openai_client
        )

        contexts = [seg["text"] for seg in short_segments]

        sample = create_ragas_sample(
            user_query="Generate session notes from brief session",
            response=document["content"],
            contexts=contexts
        )

        score = await faithfulness_metric.single_turn_ascore(sample)

        print(f"\n=== Short Session Test ===")
        print(f"Segments: {len(short_segments)}")
        print(f"Faithfulness: {score:.3f}")

        # Lower threshold for very short sessions
        assert score >= 0.7, \
            f"Short session faithfulness {score:.3f} below 0.7"

    async def test_multiple_topic_session(
        self,
        openai_client,
        faithfulness_metric,
        session_notes_template
    ):
        """
        Test faithfulness when session covers multiple distinct topics.
        """
        multi_topic_segments = [
            {
                "id": "mt-001",
                "speaker": "Client",
                "text": "I've been having trouble sleeping, maybe 4 hours a night.",
                "start_time": 0,
            },
            {
                "id": "mt-002",
                "speaker": "Therapist",
                "text": "Let's discuss sleep hygiene strategies.",
                "start_time": 10,
            },
            {
                "id": "mt-003",
                "speaker": "Client",
                "text": "Also, I had a panic attack at work last Tuesday.",
                "start_time": 120,
            },
            {
                "id": "mt-004",
                "speaker": "Therapist",
                "text": "We should practice grounding techniques for panic attacks.",
                "start_time": 130,
            },
            {
                "id": "mt-005",
                "speaker": "Client",
                "text": "My relationship with my partner has been strained too.",
                "start_time": 240,
            },
            {
                "id": "mt-006",
                "speaker": "Therapist",
                "text": "Communication skills might help with your relationship concerns.",
                "start_time": 250,
            },
        ]

        document = await generate_document_for_test(
            segments=multi_topic_segments,
            template=session_notes_template,
            client_name="Jordan Lee",
            practitioner_name="Dr. Rachel Kim",
            openai_client=openai_client
        )

        contexts = [seg["text"] for seg in multi_topic_segments]

        sample = create_ragas_sample(
            user_query="Generate session notes covering multiple topics",
            response=document["content"],
            contexts=contexts
        )

        score = await faithfulness_metric.single_turn_ascore(sample)

        # Check all topics are covered
        content_lower = document["content"].lower()
        topics = ["sleep", "panic", "relationship"]
        topics_covered = [t for t in topics if t in content_lower]

        print(f"\n=== Multi-Topic Session Test ===")
        print(f"Faithfulness: {score:.3f}")
        print(f"Topics covered: {topics_covered}")

        assert score >= 0.75, f"Multi-topic faithfulness {score:.3f} below 0.75"
        assert len(topics_covered) >= 2, f"Only {len(topics_covered)} topics covered"
