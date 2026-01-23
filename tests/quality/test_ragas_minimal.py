"""
Minimal RAGAS evaluation tests with short documents.

These tests use minimal segments and templates to avoid token limit issues.
Uses REAL OpenAI API calls.

Run with: pytest tests/quality/test_ragas_minimal.py -v
"""

import pytest
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# RAGAS imports
from ragas.metrics._faithfulness import Faithfulness
from ragas.metrics._answer_relevance import ResponseRelevancy
from ragas.dataset_schema import SingleTurnSample
from ragas.llms import llm_factory
from ragas.embeddings.base import embedding_factory

# OpenAI
from openai import OpenAI, AsyncOpenAI


# ============================================================================
# MINIMAL TEST DATA - Very short for RAGAS evaluation
# ============================================================================

MINIMAL_SEGMENTS = [
    {
        "text": "Client reported feeling better. The breathing exercises helped with anxiety.",
    },
    {
        "text": "Therapist assigned homework: practice breathing twice daily.",
    },
]

MINIMAL_CONTEXTS = [seg["text"] for seg in MINIMAL_SEGMENTS]


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def openai_client():
    """Create real OpenAI client."""
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
# TESTS WITH PRE-DEFINED SHORT DOCUMENTS
# ============================================================================

@pytest.mark.asyncio
async def test_faithfulness_short_document(faithfulness_metric):
    """
    Test RAGAS faithfulness with a pre-written short document.

    This avoids the token limit issue by using a minimal document.
    """
    # Short, faithful document
    document = """
    Sarah reported feeling better. The breathing exercises helped with anxiety.
    Homework: practice breathing twice daily.
    """

    sample = SingleTurnSample(
        user_input="Summarize the session",
        response=document.strip(),
        retrieved_contexts=MINIMAL_CONTEXTS
    )

    score = await faithfulness_metric.single_turn_ascore(sample)

    print(f"\n=== Faithfulness Score: {score:.3f} ===")

    assert score >= 0.7, f"Faithfulness {score:.3f} below threshold"


@pytest.mark.asyncio
async def test_faithfulness_unfaithful_document(faithfulness_metric):
    """
    Test that RAGAS correctly identifies unfaithful content.
    """
    # Document with hallucinated content
    unfaithful_document = """
    Sarah tried yoga and meditation. She completed 10 homework assignments.
    The therapist recommended medication changes.
    """

    sample = SingleTurnSample(
        user_input="Summarize the session",
        response=unfaithful_document.strip(),
        retrieved_contexts=MINIMAL_CONTEXTS
    )

    score = await faithfulness_metric.single_turn_ascore(sample)

    print(f"\n=== Unfaithful Document Score: {score:.3f} ===")
    print("(Lower score expected for hallucinated content)")

    # This should have a lower score due to hallucinations
    # We don't assert failure, just verify it's detected
    assert score < 0.9, f"Unfaithful document scored too high: {score:.3f}"


@pytest.mark.asyncio
async def test_relevancy_short_document(relevancy_metric):
    """
    Test RAGAS relevancy with a short document.
    """
    document = """
    Session Summary:
    - Client feeling better
    - Breathing exercises helping with anxiety
    - Homework: practice breathing twice daily
    """

    sample = SingleTurnSample(
        user_input="What were the key points and homework from the session?",
        response=document.strip(),
        retrieved_contexts=MINIMAL_CONTEXTS
    )

    score = await relevancy_metric.single_turn_ascore(sample)

    print(f"\n=== Relevancy Score: {score:.3f} ===")

    assert score >= 0.5, f"Relevancy {score:.3f} below threshold"


@pytest.mark.asyncio
async def test_generated_document_faithfulness(openai_client, faithfulness_metric):
    """
    Test faithfulness of a document generated with concise instructions.
    """
    # Generate a VERY brief document
    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "Generate ONLY a 2-3 sentence summary. Be extremely brief."
            },
            {
                "role": "user",
                "content": f"""Summarize this session in 2-3 sentences only:

Context:
{MINIMAL_CONTEXTS[0]}
{MINIMAL_CONTEXTS[1]}

Output ONLY the summary, nothing else. Maximum 50 words."""
            }
        ],
        max_tokens=100,
        temperature=0.3,
    )

    document = response.choices[0].message.content

    print(f"\n=== Generated Document ===")
    print(document)
    print("=" * 40)

    sample = SingleTurnSample(
        user_input="Summarize the session briefly",
        response=document,
        retrieved_contexts=MINIMAL_CONTEXTS
    )

    score = await faithfulness_metric.single_turn_ascore(sample)

    print(f"Faithfulness Score: {score:.3f}")

    assert score >= 0.6, f"Faithfulness {score:.3f} below threshold"


@pytest.mark.asyncio
async def test_combined_evaluation(faithfulness_metric, relevancy_metric):
    """
    Test combined RAGAS evaluation on a short document.
    """
    document = """
    Session notes: Client reported improvement since last session.
    The breathing exercises have been effective for managing anxiety.
    Next steps: Continue breathing practice twice daily as homework.
    """

    sample = SingleTurnSample(
        user_input="Document the session summary and homework",
        response=document.strip(),
        retrieved_contexts=MINIMAL_CONTEXTS
    )

    faithfulness_score = await faithfulness_metric.single_turn_ascore(sample)
    relevancy_score = await relevancy_metric.single_turn_ascore(sample)
    combined = (faithfulness_score + relevancy_score) / 2

    print("\n" + "=" * 50)
    print("COMBINED RAGAS EVALUATION")
    print("=" * 50)
    print(f"Faithfulness:  {faithfulness_score:.3f}")
    print(f"Relevancy:     {relevancy_score:.3f}")
    print(f"Combined:      {combined:.3f}")
    print("=" * 50)

    assert faithfulness_score >= 0.6, f"Faithfulness too low"
    assert relevancy_score >= 0.4, f"Relevancy too low"
    assert combined >= 0.5, f"Combined score too low"
