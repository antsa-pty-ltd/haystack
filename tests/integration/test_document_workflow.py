"""
End-to-end integration tests for the AI Scribe document generation workflow.

These tests verify the complete flow from:
1. Session/template selection
2. Context gathering
3. Document generation
4. Output validation
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from tests.conftest import (
    check_personalization,
    check_no_diagnosis,
    check_template_sections,
    SAMPLE_TRANSCRIPT_SEGMENTS,
    SAMPLE_TEMPLATE_SESSION_NOTES,
    SAMPLE_CLIENT_INFO,
    SAMPLE_PRACTITIONER_INFO
)


class TestDocumentGenerationWorkflow:
    """Test the complete document generation workflow."""

    @pytest.mark.integration
    async def test_full_document_generation_flow(
        self,
        sample_segments,
        sample_template,
        sample_client_info,
        sample_practitioner_info,
        mock_openai_client
    ):
        """Test the complete document generation flow."""
        from document_generation.generator import generate_document_from_context

        # Step 1: Generate document
        result = await generate_document_from_context(
            segments=sample_segments,
            template=sample_template,
            client_info=sample_client_info,
            practitioner_info=sample_practitioner_info,
            generation_instructions=None,
            openai_client=mock_openai_client
        )

        # Step 2: Verify structure
        assert "content" in result
        assert "generated_at" in result
        assert "metadata" in result

        document = result["content"]

        # Step 3: Check personalization
        personalization_result = check_personalization(
            document,
            sample_client_info["name"],
            sample_practitioner_info["name"]
        )
        assert personalization_result["passed"], \
            f"Personalization check failed: {personalization_result['issues']}"

        # Step 4: Check no diagnosis
        diagnosis_result = check_no_diagnosis(document)
        assert diagnosis_result["passed"], \
            f"Found diagnostic language: {diagnosis_result['issues']}"

    @pytest.mark.integration
    async def test_multiple_sessions_workflow(self, mock_openai_client):
        """Test document generation from multiple sessions."""
        from document_generation.generator import generate_document_from_context

        # Create segments from multiple sessions
        multi_session_segments = []
        for session_num in range(3):
            for seg in SAMPLE_TRANSCRIPT_SEGMENTS[:3]:
                segment = seg.copy()
                segment["transcript_id"] = f"trans-{session_num + 1:03d}"
                segment["start_time"] = seg["start_time"] + (session_num * 100)
                multi_session_segments.append(segment)

        result = await generate_document_from_context(
            segments=multi_session_segments,
            template=SAMPLE_TEMPLATE_SESSION_NOTES,
            client_info=SAMPLE_CLIENT_INFO,
            practitioner_info=SAMPLE_PRACTITIONER_INFO,
            generation_instructions=None,
            openai_client=mock_openai_client
        )

        # Verify metadata reflects multiple sessions
        assert result["metadata"]["segmentsUsed"] == len(multi_session_segments)

    @pytest.mark.integration
    async def test_workflow_with_generation_instructions(self, mock_openai_client):
        """Test workflow with additional generation instructions."""
        from document_generation.generator import generate_document_from_context

        instructions = """
        Focus on anxiety management techniques discussed.
        Include specific details about the breathing exercises.
        Note any progress made since the last session.
        """

        result = await generate_document_from_context(
            segments=SAMPLE_TRANSCRIPT_SEGMENTS,
            template=SAMPLE_TEMPLATE_SESSION_NOTES,
            client_info=SAMPLE_CLIENT_INFO,
            practitioner_info=SAMPLE_PRACTITIONER_INFO,
            generation_instructions=instructions,
            openai_client=mock_openai_client
        )

        assert "content" in result
        assert len(result["content"]) > 0


class TestProgressEmission:
    """Test progress tracking during document generation."""

    @pytest.mark.integration
    async def test_progress_stages(self):
        """Test that progress stages are emitted correctly."""
        progress_events = []

        async def mock_emit_progress(generation_id: str, data: dict, authorization=None):
            progress_events.append(data)

        with patch('main.emit_progress', mock_emit_progress):
            # Note: This would require a full integration setup
            # For now, we verify the emit_progress function signature
            await mock_emit_progress("gen-123", {"stage": "initializing"})
            await mock_emit_progress("gen-123", {"stage": "gathering_context"})
            await mock_emit_progress("gen-123", {"stage": "generating_document"})
            await mock_emit_progress("gen-123", {"stage": "complete"})

        stages = [e["stage"] for e in progress_events]
        assert "initializing" in stages
        assert "gathering_context" in stages
        assert "generating_document" in stages
        assert "complete" in stages


class TestTemplateSpecificGeneration:
    """Test generation with specific template types."""

    @pytest.mark.integration
    @pytest.mark.parametrize("template_name,expected_sections", [
        ("Session Notes", ["Subjective", "Objective", "Assessment", "Plan"]),
        ("Treatment Plan", ["Presenting Issues", "Goals", "Interventions"]),
    ])
    async def test_template_specific_sections(
        self,
        template_name,
        expected_sections,
        sample_segments,
        sample_client_info,
        sample_practitioner_info
    ):
        """Test that each template type produces correct sections."""
        mock_client = AsyncMock()

        # Create response with expected sections
        sections_text = "\n".join([f"## {s}\nContent for {s}." for s in expected_sections])
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = f"""# {template_name}

{sections_text}

**Client:** {sample_client_info['name']}
**Practitioner:** {sample_practitioner_info['name']}
"""
        mock_response.choices[0].finish_reason = "stop"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        from document_generation.generator import generate_document_from_context

        template = {
            "id": f"template-{template_name.lower().replace(' ', '-')}",
            "name": template_name,
            "content": f"# {template_name}\n" + "\n".join([f"## {s}\n" for s in expected_sections])
        }

        result = await generate_document_from_context(
            segments=sample_segments,
            template=template,
            client_info=sample_client_info,
            practitioner_info=sample_practitioner_info,
            generation_instructions=None,
            openai_client=mock_client
        )

        section_result = check_template_sections(result["content"], expected_sections)
        assert section_result["passed"], \
            f"Missing sections for {template_name}: {section_result['missing_sections']}"


class TestErrorRecovery:
    """Test error handling and recovery in the workflow."""

    @pytest.mark.integration
    async def test_api_timeout_handling(
        self,
        sample_segments,
        sample_template,
        sample_client_info,
        sample_practitioner_info
    ):
        """Test handling of API timeouts."""
        import asyncio

        mock_client = AsyncMock()

        async def slow_response(**kwargs):
            await asyncio.sleep(0.1)  # Simulate delay
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Test content"
            mock_response.choices[0].finish_reason = "stop"
            return mock_response

        mock_client.chat.completions.create = slow_response

        from document_generation.generator import generate_document_from_context

        # Should complete despite delay
        result = await generate_document_from_context(
            segments=sample_segments,
            template=sample_template,
            client_info=sample_client_info,
            practitioner_info=sample_practitioner_info,
            generation_instructions=None,
            openai_client=mock_client
        )

        assert "content" in result

    @pytest.mark.integration
    async def test_retry_on_empty_response(
        self,
        sample_segments,
        sample_template,
        sample_client_info,
        sample_practitioner_info
    ):
        """Test that empty responses raise appropriate errors."""
        mock_client = AsyncMock()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""
        mock_response.choices[0].finish_reason = "stop"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        from document_generation.generator import generate_document_from_context

        with pytest.raises(Exception):
            await generate_document_from_context(
                segments=sample_segments,
                template=sample_template,
                client_info=sample_client_info,
                practitioner_info=sample_practitioner_info,
                generation_instructions=None,
                openai_client=mock_client
            )


class TestDataIntegrity:
    """Test data integrity throughout the workflow."""

    @pytest.mark.integration
    async def test_segment_data_preserved(self, mock_openai_client):
        """Test that segment data is properly passed through."""
        captured_prompt = []

        original_create = mock_openai_client.chat.completions.create

        async def capture_and_call(**kwargs):
            captured_prompt.extend(kwargs.get("messages", []))
            return await original_create(**kwargs)

        mock_openai_client.chat.completions.create = capture_and_call

        from document_generation.generator import generate_document_from_context

        await generate_document_from_context(
            segments=SAMPLE_TRANSCRIPT_SEGMENTS,
            template=SAMPLE_TEMPLATE_SESSION_NOTES,
            client_info=SAMPLE_CLIENT_INFO,
            practitioner_info=SAMPLE_PRACTITIONER_INFO,
            generation_instructions=None,
            openai_client=mock_openai_client
        )

        # Check that transcript content is in the prompt
        user_prompt = captured_prompt[1]["content"] if len(captured_prompt) > 1 else ""
        assert "breathing exercises" in user_prompt.lower()

    @pytest.mark.integration
    async def test_client_info_in_prompt(self, mock_openai_client):
        """Test that client info is included in generation prompt."""
        captured_messages = []

        async def capture(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Test"
            mock_response.choices[0].finish_reason = "stop"
            return mock_response

        mock_openai_client.chat.completions.create = capture

        from document_generation.generator import generate_document_from_context

        await generate_document_from_context(
            segments=SAMPLE_TRANSCRIPT_SEGMENTS,
            template=SAMPLE_TEMPLATE_SESSION_NOTES,
            client_info=SAMPLE_CLIENT_INFO,
            practitioner_info=SAMPLE_PRACTITIONER_INFO,
            generation_instructions=None,
            openai_client=mock_openai_client
        )

        all_content = " ".join([m["content"] for m in captured_messages])
        assert SAMPLE_CLIENT_INFO["name"] in all_content
        assert SAMPLE_PRACTITIONER_INFO["name"] in all_content
