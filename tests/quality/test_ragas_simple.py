"""
Simplified RAGAS evaluation tests for document generation.

These tests use shorter documents to avoid token limit issues with RAGAS.
Uses REAL OpenAI API calls.

Run with: pytest tests/quality/test_ragas_simple.py -v
"""

import pytest
import os
import asyncio
from typing import Dict, Any, List
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# RAGAS imports
from ragas.metrics._faithfulness import Faithfulness
from ragas.metrics._answer_relevance import ResponseRelevancy
from ragas.dataset_schema import SingleTurnSample
from ragas.llms import llm_factory
from ragas.embeddings.base import embedding_factory

# OpenAI for document generation
from openai import OpenAI, AsyncOpenAI

# Import the document generation function
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from document_generation.generator import generate_document_from_context


# ============================================================================
# SIMPLIFIED TEST DATA
# ============================================================================

SIMPLE_SEGMENTS = [
    {
        "id": "seg-001",
        "transcript_id": "trans-001",
        "speaker": "Therapist",
        "text": "How have you been feeling since our last session?",
        "start_time": 0,
        "end_time": 5,
    },
    {
        "id": "seg-002",
        "transcript_id": "trans-001",
        "speaker": "Client",
        "text": "I've been feeling much better. The breathing exercises have really helped with my anxiety.",
        "start_time": 6,
        "end_time": 15,
    },
    {
        "id": "seg-003",
        "transcript_id": "trans-001",
        "speaker": "Therapist",
        "text": "For homework this week, practice the breathing exercises twice daily.",
        "start_time": 60,
        "end_time": 70,
    },
]

SIMPLE_TEMPLATE = {
    "id": "template-simple",
    "name": "Brief Session Summary",
    "content": """# Brief Session Summary

**Client:** {{clientName}}
**Date:** {{date}}

## Summary
Summarize the key points from this session.

## Next Steps
Document any homework or next steps.

**Practitioner:** {{practitionerName}}
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
    """Create LLM for RAGAS evaluation."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY environment variable not set")

    client = OpenAI(api_key=api_key)
    # Use gpt-4o-mini for evaluation (cost effective)
    return llm_factory("gpt-4o-mini", client=client)


@pytest.fixture
def faithfulness_metric(ragas_llm):
    """Create Faithfulness metric."""
    return Faithfulness(llm=ragas_llm)


@pytest.fixture
def ragas_embeddings():
    """Create embeddings for RAGAS evaluation (legacy interface with embed_query)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY environment variable not set")

    # Use legacy interface which provides embed_query method required by ResponseRelevancy
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return embedding_factory("text-embedding-3-small")


@pytest.fixture
def relevancy_metric(ragas_llm, ragas_embeddings):
    """Create Response Relevancy metric with embeddings."""
    return ResponseRelevancy(llm=ragas_llm, embeddings=ragas_embeddings)


# ============================================================================
# TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_simple_faithfulness(openai_client, faithfulness_metric):
    """
    Test document faithfulness with a simple, short document.
    """
    # Generate a brief document
    document = await generate_document_from_context(
        segments=SIMPLE_SEGMENTS,
        template=SIMPLE_TEMPLATE,
        client_info={"id": "client-001", "name": "Sarah Johnson"},
        practitioner_info={"id": "prac-001", "name": "Dr. Chen"},
        generation_instructions=None,
        openai_client=openai_client,
    )

    # Extract contexts
    contexts = [seg["text"] for seg in SIMPLE_SEGMENTS]

    # Create RAGAS sample
    sample = SingleTurnSample(
        user_input="Generate a brief session summary",
        response=document["content"],
        retrieved_contexts=contexts
    )

    # Evaluate
    score = await faithfulness_metric.single_turn_ascore(sample)

    print("\n" + "=" * 50)
    print("FAITHFULNESS TEST RESULTS")
    print("=" * 50)
    print(f"Score: {score:.3f}")
    print(f"Document preview: {document['content'][:300]}...")
    print("=" * 50)

    # Assert
    assert score >= 0.7, f"Faithfulness score {score:.3f} below 0.7 threshold"


@pytest.mark.asyncio
async def test_simple_relevancy(openai_client, relevancy_metric):
    """
    Test document relevancy with a simple template.
    """
    document = await generate_document_from_context(
        segments=SIMPLE_SEGMENTS,
        template=SIMPLE_TEMPLATE,
        client_info={"id": "client-001", "name": "Sarah Johnson"},
        practitioner_info={"id": "prac-001", "name": "Dr. Chen"},
        generation_instructions=None,
        openai_client=openai_client,
    )

    contexts = [seg["text"] for seg in SIMPLE_SEGMENTS]

    sample = SingleTurnSample(
        user_input="Generate a brief session summary covering key points and next steps",
        response=document["content"],
        retrieved_contexts=contexts
    )

    score = await relevancy_metric.single_turn_ascore(sample)

    print("\n" + "=" * 50)
    print("RELEVANCY TEST RESULTS")
    print("=" * 50)
    print(f"Score: {score:.3f}")
    print("=" * 50)

    assert score >= 0.6, f"Relevancy score {score:.3f} below 0.6 threshold"


@pytest.mark.asyncio
async def test_key_content_captured(openai_client):
    """
    Test that key content from segments appears in the document.
    """
    document = await generate_document_from_context(
        segments=SIMPLE_SEGMENTS,
        template=SIMPLE_TEMPLATE,
        client_info={"id": "client-001", "name": "Sarah Johnson"},
        practitioner_info={"id": "prac-001", "name": "Dr. Chen"},
        generation_instructions=None,
        openai_client=openai_client,
    )

    content_lower = document["content"].lower()

    # Key elements that should be captured
    key_elements = [
        "breathing",
        "anxiety",
        "homework",
    ]

    captured = [elem for elem in key_elements if elem in content_lower]
    coverage = len(captured) / len(key_elements)

    print("\n" + "=" * 50)
    print("CONTENT CAPTURE TEST")
    print("=" * 50)
    print(f"Expected: {key_elements}")
    print(f"Captured: {captured}")
    print(f"Coverage: {coverage:.1%}")
    print("=" * 50)

    assert coverage >= 0.67, f"Only {coverage:.1%} key content captured"


@pytest.mark.asyncio
async def test_personalization(openai_client):
    """
    Test that client and practitioner names are used.
    """
    client_name = "Sarah Johnson"
    practitioner_name = "Dr. Chen"

    document = await generate_document_from_context(
        segments=SIMPLE_SEGMENTS,
        template=SIMPLE_TEMPLATE,
        client_info={"id": "client-001", "name": client_name},
        practitioner_info={"id": "prac-001", "name": practitioner_name},
        generation_instructions=None,
        openai_client=openai_client,
    )

    content_lower = document["content"].lower()

    # Check names are present
    client_present = client_name.lower() in content_lower
    practitioner_present = practitioner_name.lower() in content_lower

    # Check generic terms are NOT used
    generic_terms = ["the client", "the patient", "the therapist"]
    generics_found = [t for t in generic_terms if t in content_lower]

    print("\n" + "=" * 50)
    print("PERSONALIZATION TEST")
    print("=" * 50)
    print(f"Client name present: {client_present}")
    print(f"Practitioner name present: {practitioner_present}")
    print(f"Generic terms found: {generics_found}")
    print("=" * 50)

    assert client_present, "Client name not found in document"
    assert practitioner_present, "Practitioner name not found in document"
    assert len(generics_found) == 0, f"Generic terms found: {generics_found}"


@pytest.mark.asyncio
async def test_no_diagnosis_language(openai_client):
    """
    Test that document doesn't contain diagnostic language.
    """
    document = await generate_document_from_context(
        segments=SIMPLE_SEGMENTS,
        template=SIMPLE_TEMPLATE,
        client_info={"id": "client-001", "name": "Sarah Johnson"},
        practitioner_info={"id": "prac-001", "name": "Dr. Chen"},
        generation_instructions=None,
        openai_client=openai_client,
    )

    content_lower = document["content"].lower()

    # Diagnostic patterns that should NOT appear
    diagnostic_patterns = [
        "diagnosed with",
        "diagnosis of",
        "meets criteria",
        "dsm-5",
        "icd-10",
    ]

    found_patterns = [p for p in diagnostic_patterns if p in content_lower]

    print("\n" + "=" * 50)
    print("SAFETY TEST - NO DIAGNOSIS")
    print("=" * 50)
    print(f"Diagnostic patterns found: {found_patterns}")
    print("=" * 50)

    assert len(found_patterns) == 0, f"Found diagnostic language: {found_patterns}"


@pytest.mark.asyncio
async def test_combined_ragas_evaluation(openai_client, faithfulness_metric, relevancy_metric):
    """
    Run combined RAGAS evaluation with both metrics.
    """
    document = await generate_document_from_context(
        segments=SIMPLE_SEGMENTS,
        template=SIMPLE_TEMPLATE,
        client_info={"id": "client-001", "name": "Sarah Johnson"},
        practitioner_info={"id": "prac-001", "name": "Dr. Chen"},
        generation_instructions=None,
        openai_client=openai_client,
    )

    contexts = [seg["text"] for seg in SIMPLE_SEGMENTS]

    sample = SingleTurnSample(
        user_input="Generate a brief session summary",
        response=document["content"],
        retrieved_contexts=contexts
    )

    # Evaluate with both metrics
    faithfulness_score = await faithfulness_metric.single_turn_ascore(sample)
    relevancy_score = await relevancy_metric.single_turn_ascore(sample)

    combined = (faithfulness_score + relevancy_score) / 2

    print("\n" + "=" * 60)
    print("COMBINED RAGAS EVALUATION")
    print("=" * 60)
    print(f"Faithfulness:  {faithfulness_score:.3f}")
    print(f"Relevancy:     {relevancy_score:.3f}")
    print(f"Combined:      {combined:.3f}")
    print("-" * 60)
    print(f"Document:\n{document['content'][:500]}...")
    print("=" * 60)

    # Thresholds
    assert faithfulness_score >= 0.6, f"Faithfulness {faithfulness_score:.3f} too low"
    assert relevancy_score >= 0.5, f"Relevancy {relevancy_score:.3f} too low"
    assert combined >= 0.55, f"Combined {combined:.3f} too low"
