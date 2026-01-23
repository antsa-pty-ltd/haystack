"""
Tests for document generation in AI Scribe.

These tests verify:
- Document generation from transcript segments
- Template variable substitution
- Section completeness
- Metadata generation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from tests.conftest import (
    check_template_sections,
    check_variable_substitution,
    check_no_diagnosis,
    VARIABLE_SUBSTITUTION_CASES
)


class TestDocumentGeneration:
    """Test suite for document generation."""

    @pytest.mark.unit
    async def test_basic_document_generation(
        self,
        sample_segments,
        sample_template,
        sample_client_info,
        sample_practitioner_info,
        mock_openai_client
    ):
        """Test basic document generation produces valid output."""
        from document_generation.generator import generate_document_from_context

        result = await generate_document_from_context(
            segments=sample_segments,
            template=sample_template,
            client_info=sample_client_info,
            practitioner_info=sample_practitioner_info,
            generation_instructions=None,
            openai_client=mock_openai_client
        )

        assert "content" in result
        assert "generated_at" in result
        assert "metadata" in result
        assert len(result["content"]) > 0

    @pytest.mark.unit
    async def test_document_metadata(
        self,
        sample_segments,
        sample_template,
        sample_client_info,
        sample_practitioner_info,
        mock_openai_client
    ):
        """Test that document metadata is correctly populated."""
        from document_generation.generator import generate_document_from_context

        result = await generate_document_from_context(
            segments=sample_segments,
            template=sample_template,
            client_info=sample_client_info,
            practitioner_info=sample_practitioner_info,
            generation_instructions=None,
            openai_client=mock_openai_client
        )

        metadata = result["metadata"]
        assert metadata["templateId"] == sample_template["id"]
        assert metadata["templateName"] == sample_template["name"]
        assert metadata["clientId"] == sample_client_info["id"]
        assert metadata["practitionerId"] == sample_practitioner_info["id"]
        assert metadata["segmentsUsed"] == len(sample_segments)
        assert "wordCount" in metadata

    @pytest.mark.unit
    async def test_document_timestamp(
        self,
        sample_segments,
        sample_template,
        sample_client_info,
        sample_practitioner_info,
        mock_openai_client
    ):
        """Test that document timestamp is valid ISO format."""
        from document_generation.generator import generate_document_from_context

        result = await generate_document_from_context(
            segments=sample_segments,
            template=sample_template,
            client_info=sample_client_info,
            practitioner_info=sample_practitioner_info,
            generation_instructions=None,
            openai_client=mock_openai_client
        )

        # Should be valid ISO format
        timestamp = result["generated_at"]
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

    @pytest.mark.unit
    async def test_generation_with_instructions(
        self,
        sample_segments,
        sample_template,
        sample_client_info,
        sample_practitioner_info
    ):
        """Test that additional generation instructions are included."""
        mock_client = AsyncMock()
        captured_messages = []

        async def capture_messages(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Test content"
            mock_response.choices[0].finish_reason = "stop"
            return mock_response

        mock_client.chat.completions.create = capture_messages

        from document_generation.generator import generate_document_from_context

        instructions = "Focus on anxiety management techniques discussed."

        await generate_document_from_context(
            segments=sample_segments,
            template=sample_template,
            client_info=sample_client_info,
            practitioner_info=sample_practitioner_info,
            generation_instructions=instructions,
            openai_client=mock_client
        )

        system_prompt = captured_messages[0]["content"]
        assert instructions in system_prompt or "ADDITIONAL CONTEXT" in system_prompt


class TestVariableSubstitution:
    """Test template variable substitution."""

    @pytest.mark.unit
    @pytest.mark.parametrize("case", VARIABLE_SUBSTITUTION_CASES)
    def test_variable_substitution_helper(self, case):
        """Test the variable substitution check helper."""
        # Simulate a document where variables have been substituted
        substituted_doc = case["template"]
        for var, value in case["variables"].items():
            substituted_doc = substituted_doc.replace(f"{{{{{var}}}}}", value)

        # Check expected values are present
        for expected in case["expected_contains"]:
            assert expected in substituted_doc

        # Check template variables are gone
        result = check_variable_substitution(substituted_doc, case["expected_not_contains"])
        assert result["passed"], f"Unsubstituted variables: {result['unsubstituted']}"

    @pytest.mark.unit
    async def test_prompt_includes_variable_instructions(
        self,
        sample_segments,
        sample_template,
        sample_client_info,
        sample_practitioner_info
    ):
        """Test that the prompt instructs to replace template variables."""
        mock_client = AsyncMock()
        captured_messages = []

        async def capture_messages(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Test"
            mock_response.choices[0].finish_reason = "stop"
            return mock_response

        mock_client.chat.completions.create = capture_messages

        from document_generation.generator import generate_document_from_context

        await generate_document_from_context(
            segments=sample_segments,
            template=sample_template,
            client_info=sample_client_info,
            practitioner_info=sample_practitioner_info,
            generation_instructions=None,
            openai_client=mock_client
        )

        user_prompt = captured_messages[1]["content"]
        assert "Replace template placeholders" in user_prompt or "{{" in user_prompt


class TestTemplateSections:
    """Test template section handling."""

    @pytest.mark.unit
    def test_section_check_helper(self):
        """Test the section check helper function."""
        document = """
        # Session Notes

        ## Subjective
        Client reported feeling better.

        ## Objective
        Client appeared calm.

        ## Assessment
        Good progress noted.

        ## Plan
        Continue current approach.
        """

        expected = ["Subjective", "Objective", "Assessment", "Plan"]
        result = check_template_sections(document, expected)

        assert result["passed"]
        assert len(result["missing_sections"]) == 0

    @pytest.mark.unit
    def test_missing_sections_detected(self):
        """Test that missing sections are detected."""
        incomplete_doc = """
        # Session Notes

        ## Subjective
        Client reported feeling better.

        ## Plan
        Continue therapy.
        """

        expected = ["Subjective", "Objective", "Assessment", "Plan"]
        result = check_template_sections(incomplete_doc, expected)

        assert not result["passed"]
        assert "Objective" in result["missing_sections"]
        assert "Assessment" in result["missing_sections"]


class TestSegmentProcessing:
    """Test transcript segment processing."""

    @pytest.mark.unit
    async def test_segments_sorted_chronologically(
        self,
        sample_template,
        sample_client_info,
        sample_practitioner_info
    ):
        """Test that segments are sorted by start_time."""
        mock_client = AsyncMock()
        captured_messages = []

        async def capture_messages(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Test"
            mock_response.choices[0].finish_reason = "stop"
            return mock_response

        mock_client.chat.completions.create = capture_messages

        # Out-of-order segments
        unsorted_segments = [
            {"speaker": "Speaker 0", "text": "Third", "start_time": 30, "transcript_id": "t1"},
            {"speaker": "Speaker 0", "text": "First", "start_time": 0, "transcript_id": "t1"},
            {"speaker": "Speaker 0", "text": "Second", "start_time": 15, "transcript_id": "t1"},
        ]

        from document_generation.generator import generate_document_from_context

        await generate_document_from_context(
            segments=unsorted_segments,
            template=sample_template,
            client_info=sample_client_info,
            practitioner_info=sample_practitioner_info,
            generation_instructions=None,
            openai_client=mock_client
        )

        user_prompt = captured_messages[1]["content"]
        # Check that segments appear in chronological order
        first_pos = user_prompt.find("First")
        second_pos = user_prompt.find("Second")
        third_pos = user_prompt.find("Third")

        assert first_pos < second_pos < third_pos, "Segments should be sorted chronologically"

    @pytest.mark.unit
    async def test_time_formatting(
        self,
        sample_template,
        sample_client_info,
        sample_practitioner_info
    ):
        """Test that segment times are formatted correctly."""
        mock_client = AsyncMock()
        captured_messages = []

        async def capture_messages(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Test"
            mock_response.choices[0].finish_reason = "stop"
            return mock_response

        mock_client.chat.completions.create = capture_messages

        segments = [
            {"speaker": "Speaker 0", "text": "Test", "start_time": 125, "transcript_id": "t1"},  # 2:05
        ]

        from document_generation.generator import generate_document_from_context

        await generate_document_from_context(
            segments=segments,
            template=sample_template,
            client_info=sample_client_info,
            practitioner_info=sample_practitioner_info,
            generation_instructions=None,
            openai_client=mock_client
        )

        user_prompt = captured_messages[1]["content"]
        # Check for MM:SS format
        assert "[02:05]" in user_prompt, "Time should be formatted as MM:SS"


class TestEmptyAndEdgeCases:
    """Test edge cases in document generation."""

    @pytest.mark.unit
    async def test_empty_segments(
        self,
        sample_template,
        sample_client_info,
        sample_practitioner_info,
        mock_openai_client
    ):
        """Test generation with empty segments."""
        from document_generation.generator import generate_document_from_context

        result = await generate_document_from_context(
            segments=[],
            template=sample_template,
            client_info=sample_client_info,
            practitioner_info=sample_practitioner_info,
            generation_instructions=None,
            openai_client=mock_openai_client
        )

        assert "content" in result
        assert result["metadata"]["segmentsUsed"] == 0

    @pytest.mark.unit
    async def test_openai_error_handling(
        self,
        sample_segments,
        sample_template,
        sample_client_info,
        sample_practitioner_info
    ):
        """Test handling of OpenAI API errors."""
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("API Error")
        )

        from document_generation.generator import generate_document_from_context

        with pytest.raises(Exception) as exc_info:
            await generate_document_from_context(
                segments=sample_segments,
                template=sample_template,
                client_info=sample_client_info,
                practitioner_info=sample_practitioner_info,
                generation_instructions=None,
                openai_client=mock_client
            )

        assert "API Error" in str(exc_info.value) or "Error" in str(exc_info.value)

    @pytest.mark.unit
    async def test_empty_response_handling(
        self,
        sample_segments,
        sample_template,
        sample_client_info,
        sample_practitioner_info
    ):
        """Test handling of empty OpenAI responses."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""
        mock_response.choices[0].finish_reason = "stop"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        from document_generation.generator import generate_document_from_context

        with pytest.raises(Exception) as exc_info:
            await generate_document_from_context(
                segments=sample_segments,
                template=sample_template,
                client_info=sample_client_info,
                practitioner_info=sample_practitioner_info,
                generation_instructions=None,
                openai_client=mock_client
            )

        assert "No content" in str(exc_info.value) or "failed" in str(exc_info.value).lower()


class TestAntiDiagnosisInstructions:
    """Test that anti-diagnosis instructions are included."""

    @pytest.mark.unit
    @pytest.mark.safety
    async def test_system_prompt_has_anti_diagnosis(
        self,
        sample_segments,
        sample_template,
        sample_client_info,
        sample_practitioner_info
    ):
        """Test that system prompt contains anti-diagnosis instructions."""
        mock_client = AsyncMock()
        captured_messages = []

        async def capture_messages(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Test"
            mock_response.choices[0].finish_reason = "stop"
            return mock_response

        mock_client.chat.completions.create = capture_messages

        from document_generation.generator import generate_document_from_context

        await generate_document_from_context(
            segments=sample_segments,
            template=sample_template,
            client_info=sample_client_info,
            practitioner_info=sample_practitioner_info,
            generation_instructions=None,
            openai_client=mock_client
        )

        system_prompt = captured_messages[0]["content"]

        # Check for key anti-diagnosis phrases
        assert "NEVER provide, suggest, or imply any medical diagnoses" in system_prompt
        assert "NEVER diagnose mental health conditions" in system_prompt
        assert "presenting concerns" in system_prompt.lower() or "reported symptoms" in system_prompt.lower()
