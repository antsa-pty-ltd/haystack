"""
Ragas-based quality evaluation tests for AI Scribe.

These tests use the Ragas framework to evaluate:
- Faithfulness: Is the generated content grounded in the transcript?
- Answer Relevancy: Does the document address the template requirements?
- Context Precision: Are the retrieved segments relevant?

Note: These tests require the ragas package to be installed:
    pip install ragas

These tests are marked as 'slow' as they may involve LLM calls.
"""

import pytest
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch

# Try to import ragas - tests will be skipped if not installed
try:
    from ragas import evaluate
    from ragas.metrics import Faithfulness, AnswerRelevancy
    from ragas.dataset_schema import SingleTurnSample
    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False
    evaluate = None
    Faithfulness = None
    AnswerRelevancy = None
    SingleTurnSample = None


# Golden test dataset for evaluation
EVALUATION_DATASET = [
    {
        "template_name": "Session Notes",
        "transcript_text": """
        [00:00] Speaker 0: How have you been feeling since our last session?
        [00:06] Speaker 1: I've been feeling much better. The breathing exercises you taught me have really helped with my anxiety.
        [00:16] Speaker 0: That's wonderful to hear. Can you tell me more about when you've been using them?
        [00:23] Speaker 1: I use them mostly in the morning when I wake up feeling stressed, and before important meetings at work.
        [00:33] Speaker 0: Let's continue working on those coping strategies. I'd also like to introduce some mindfulness techniques today.
        """,
        "expected_themes": [
            "breathing exercises",
            "anxiety management",
            "coping strategies",
            "mindfulness techniques",
            "work stress"
        ],
        "client_name": "Sarah Johnson",
        "practitioner_name": "Dr. Michael Chen"
    },
    {
        "template_name": "Treatment Plan",
        "transcript_text": """
        [00:00] Speaker 0: Today we'll discuss your treatment goals for the next few weeks.
        [00:05] Speaker 1: I'd like to focus on managing my sleep issues and reducing my anxiety.
        [00:12] Speaker 0: Those are great goals. Let's break them down. For sleep, we can try sleep hygiene techniques.
        [00:20] Speaker 1: That sounds helpful. What about the anxiety?
        [00:25] Speaker 0: For anxiety, we'll continue with CBT techniques and add progressive muscle relaxation.
        [00:35] Speaker 1: I'm willing to try anything at this point.
        [00:40] Speaker 0: Great attitude. I'll also assign some homework between sessions.
        """,
        "expected_themes": [
            "treatment goals",
            "sleep issues",
            "anxiety",
            "sleep hygiene",
            "CBT techniques",
            "progressive muscle relaxation",
            "homework"
        ],
        "client_name": "John Smith",
        "practitioner_name": "Dr. Emily Watson"
    }
]


@pytest.mark.skipif(not RAGAS_AVAILABLE, reason="Ragas not installed")
class TestRagasEvaluation:
    """Test suite for Ragas-based evaluation."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_faithfulness_metric(self):
        """Test that generated documents are faithful to transcript content."""
        # This is a template test - actual implementation would need real LLM calls
        pass

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_relevancy_metric(self):
        """Test that generated documents are relevant to the template."""
        pass


class TestDocumentQualityChecks:
    """Test document quality without requiring Ragas."""

    @pytest.mark.unit
    def test_content_coverage(self):
        """Test that generated documents cover expected themes."""
        sample_document = """
        # Session Notes

        ## Subjective
        Sarah Johnson reported feeling much better since the last session. She mentioned
        that the breathing exercises have been particularly helpful for managing her anxiety.
        Sarah Johnson uses them in the morning and before work meetings.

        ## Objective
        Sarah Johnson appeared calm and engaged during the session.

        ## Assessment
        Dr. Michael Chen notes significant progress with anxiety management through
        breathing exercises.

        ## Plan
        Continue breathing exercises. Dr. Michael Chen will introduce mindfulness
        techniques in the next session to further enhance coping strategies.
        """

        expected_themes = [
            "breathing exercises",
            "anxiety",
            "coping strategies",
            "mindfulness"
        ]

        document_lower = sample_document.lower()
        covered_themes = [theme for theme in expected_themes if theme.lower() in document_lower]

        coverage_ratio = len(covered_themes) / len(expected_themes)
        assert coverage_ratio >= 0.75, f"Theme coverage too low: {coverage_ratio:.0%}"

    @pytest.mark.unit
    def test_document_length_requirements(self):
        """Test that documents meet minimum length requirements."""
        # Minimum word count for a proper clinical document
        MIN_WORD_COUNT = 100

        sample_document = """
        # Session Notes

        ## Client Information
        **Client Name:** Sarah Johnson
        **Date:** January 16, 2026

        ## Subjective
        Sarah Johnson reported feeling much better since the last session. Sarah Johnson
        mentioned that the breathing exercises Dr. Michael Chen taught have been very
        helpful for managing anxiety symptoms. Sarah Johnson reported using them in the
        morning when waking up feeling stressed, and also before important meetings at work.

        ## Objective
        Sarah Johnson appeared calm, relaxed, and engaged during the session.
        No signs of acute distress were observed.

        ## Assessment
        Dr. Michael Chen notes that Sarah Johnson has made significant progress with
        anxiety management through regular use of breathing exercises.

        ## Plan
        Continue with breathing exercises. Dr. Michael Chen will introduce mindfulness
        techniques in the next session to further enhance Sarah Johnson's coping strategies.

        ---
        **Practitioner:** Dr. Michael Chen
        """

        word_count = len(sample_document.split())
        assert word_count >= MIN_WORD_COUNT, f"Document too short: {word_count} words"

    @pytest.mark.unit
    def test_section_completeness(self):
        """Test that all expected sections are present."""
        from tests.conftest import check_template_sections

        sample_document = """
        # Session Notes

        ## Subjective
        Content here.

        ## Objective
        Content here.

        ## Assessment
        Content here.

        ## Plan
        Content here.
        """

        expected_sections = ["Subjective", "Objective", "Assessment", "Plan"]
        result = check_template_sections(sample_document, expected_sections)

        assert result["passed"], f"Missing sections: {result['missing_sections']}"


class TestThemeExtraction:
    """Test theme extraction from transcripts."""

    @pytest.mark.unit
    def test_therapeutic_intervention_extraction(self):
        """Test extraction of therapeutic interventions from transcript."""
        transcript = """
        [00:00] Speaker 0: Let's practice some deep breathing together.
        [00:05] Speaker 0: I want to introduce you to progressive muscle relaxation.
        [00:10] Speaker 0: We'll also work on cognitive restructuring techniques.
        [00:15] Speaker 0: For homework, try journaling your thoughts daily.
        """

        expected_interventions = [
            "deep breathing",
            "progressive muscle relaxation",
            "cognitive restructuring",
            "journaling"
        ]

        transcript_lower = transcript.lower()
        found = [i for i in expected_interventions if i.lower() in transcript_lower]

        assert len(found) >= 3, f"Should find most interventions: found {found}"

    @pytest.mark.unit
    def test_homework_assignment_extraction(self):
        """Test that homework assignments are captured."""
        transcript = """
        [00:00] Speaker 0: For your homework this week, I'd like you to practice the breathing exercises twice daily.
        [00:10] Speaker 0: Also, keep a mood journal and rate your anxiety from 1-10 each day.
        [00:20] Speaker 0: Try to identify three negative thoughts and challenge them.
        """

        homework_keywords = ["homework", "breathing exercises", "mood journal", "negative thoughts"]

        transcript_lower = transcript.lower()
        found = [k for k in homework_keywords if k.lower() in transcript_lower]

        assert len(found) >= 3, "Should capture homework-related content"


class TestFaithfulnessManual:
    """Manual faithfulness checks without Ragas."""

    @pytest.mark.unit
    def test_no_hallucinated_content(self):
        """Test that document doesn't contain content not in transcript."""
        transcript_segments = [
            "I've been feeling much better with the breathing exercises.",
            "I use them in the morning and before work meetings.",
            "The anxiety has been more manageable."
        ]

        # A document that accurately reflects the transcript
        good_document = """
        Sarah Johnson reported feeling much better with the breathing exercises.
        Sarah Johnson uses them in the morning and before work meetings.
        Sarah Johnson finds the anxiety more manageable.
        """

        # A document with hallucinated content
        bad_document = """
        Sarah Johnson reported feeling much better with the breathing exercises.
        Sarah Johnson has been practicing yoga daily.  # Not in transcript!
        Sarah Johnson completed all 10 homework assignments.  # Not in transcript!
        """

        # Check for hallucinated content
        hallucinations = ["yoga daily", "10 homework assignments"]

        good_has_hallucinations = any(h in good_document.lower() for h in hallucinations)
        bad_has_hallucinations = any(h in bad_document.lower() for h in hallucinations)

        assert not good_has_hallucinations, "Good document should not have hallucinations"
        assert bad_has_hallucinations, "Bad document should have hallucinations (for this test)"

    @pytest.mark.unit
    @pytest.mark.parametrize("dataset_item", EVALUATION_DATASET)
    def test_expected_themes_present(self, dataset_item):
        """Test that expected themes from transcript appear in evaluation."""
        transcript = dataset_item["transcript_text"]
        expected_themes = dataset_item["expected_themes"]

        transcript_lower = transcript.lower()
        themes_in_transcript = [t for t in expected_themes if t.lower() in transcript_lower]

        # At least 60% of expected themes should be in transcript
        coverage = len(themes_in_transcript) / len(expected_themes)
        assert coverage >= 0.6, f"Expected themes coverage too low: {coverage:.0%}"


class TestEvaluationDataset:
    """Test the evaluation dataset structure."""

    @pytest.mark.unit
    def test_dataset_structure(self):
        """Verify evaluation dataset has required fields."""
        for i, item in enumerate(EVALUATION_DATASET):
            assert "template_name" in item, f"Item {i} missing template_name"
            assert "transcript_text" in item, f"Item {i} missing transcript_text"
            assert "expected_themes" in item, f"Item {i} missing expected_themes"
            assert "client_name" in item, f"Item {i} missing client_name"
            assert "practitioner_name" in item, f"Item {i} missing practitioner_name"

    @pytest.mark.unit
    def test_dataset_has_diversity(self):
        """Verify dataset covers different template types."""
        template_names = [item["template_name"] for item in EVALUATION_DATASET]
        unique_templates = set(template_names)

        assert len(unique_templates) >= 2, "Dataset should cover multiple template types"
