"""
Streaming Response Behavior Integration Tests

Tests the streaming response functionality:
- Chunk ordering and delivery
- Empty chunk handling
- Full content accumulation
- Streaming reliability

Integration Points:
- Pipeline ↔ OpenAI (streaming responses)
- Pipeline ↔ WebSocket (chunk delivery)
- Chunk accumulation logic
"""

import os
import sys
# Add haystack directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from typing import List, Dict, Any

# Mark all tests as integration tests
pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class TestStreamingChunkOrdering:
    """Tests for streaming chunk order preservation"""

    async def test_chunks_arrive_in_correct_order(self):
        """
        Test that streaming chunks are delivered in the correct order.

        Flow:
        1. Mock OpenAI to return 10 specific chunks in order
        2. Generate response using pipeline
        3. Collect all chunks
        4. Verify chunks arrive in exact order sent

        This tests:
        - Chunk ordering preservation
        - No chunk reordering during async iteration
        - Stream integrity
        """
        from pipeline_manager import PipelineManager
        from personas import PersonaType
        from session_manager import session_manager

        # Create test chunks in specific order
        test_chunks = [
            "First", " chunk", " second", " chunk", " third",
            " chunk", " fourth", " chunk", " fifth", " chunk"
        ]

        # Mock OpenAI streaming response
        async def mock_stream(*args, **kwargs):
            """Mock OpenAI stream that yields chunks in order"""
            for chunk_text in test_chunks:
                mock_chunk = MagicMock()
                mock_choice = MagicMock()
                mock_delta = MagicMock()
                mock_delta.content = chunk_text
                mock_delta.tool_calls = None
                mock_choice.delta = mock_delta
                mock_choice.finish_reason = None
                mock_chunk.choices = [mock_choice]
                yield mock_chunk

        # Initialize pipeline
        pipeline = PipelineManager()
        pipeline.openai_client = AsyncMock()
        pipeline.openai_client.chat.completions.create = AsyncMock(return_value=mock_stream())
        pipeline._initialized = True

        # Create test session
        session_id = await session_manager.create_session(
            persona_type="web_assistant",
            context={},
            auth_token="test_token"
        )

        try:
            # Generate response and collect chunks
            collected_chunks: List[str] = []

            async for chunk in pipeline.generate_response(
                session_id=session_id,
                persona_type=PersonaType.WEB_ASSISTANT,
                user_message="Test streaming order",
                context={"user_id": "test_user"}
            ):
                collected_chunks.append(chunk)

            # Verify chunks arrived in correct order
            assert len(collected_chunks) == len(test_chunks), \
                f"Should receive all {len(test_chunks)} chunks, got {len(collected_chunks)}"

            for i, expected_chunk in enumerate(test_chunks):
                assert collected_chunks[i] == expected_chunk, \
                    f"Chunk {i} should be '{expected_chunk}', got '{collected_chunks[i]}'"

            # Verify accumulated content matches expected
            full_content = "".join(collected_chunks)
            expected_full = "".join(test_chunks)
            assert full_content == expected_full, \
                f"Full content should be '{expected_full}', got '{full_content}'"

        finally:
            # Cleanup
            await session_manager.delete_session(session_id)

    async def test_streaming_with_interleaved_tool_calls(self):
        """
        Test that streaming handles tool calls without corrupting order.

        Flow:
        1. Mock OpenAI to return: chunk -> tool_call -> chunk
        2. Generate response
        3. Verify text chunks remain in order (tool calls filtered out)

        This tests:
        - Tool call filtering during streaming
        - Text chunk continuity
        - Mixed response handling
        """
        from pipeline_manager import PipelineManager
        from personas import PersonaType
        from session_manager import session_manager

        # Mock streaming with text and tool calls
        async def mock_mixed_stream(*args, **kwargs):
            # First text chunk
            mock_chunk1 = MagicMock()
            mock_choice1 = MagicMock()
            mock_delta1 = MagicMock()
            mock_delta1.content = "Let me"
            mock_delta1.tool_calls = None
            mock_choice1.delta = mock_delta1
            mock_choice1.finish_reason = None
            mock_chunk1.choices = [mock_choice1]
            yield mock_chunk1

            # Tool call (should be filtered in streaming)
            mock_chunk2 = MagicMock()
            mock_choice2 = MagicMock()
            mock_delta2 = MagicMock()
            mock_delta2.content = None
            mock_delta2.tool_calls = [MagicMock(id="call_123")]
            mock_choice2.delta = mock_delta2
            mock_choice2.finish_reason = None
            mock_chunk2.choices = [mock_choice2]
            yield mock_chunk2

            # Second text chunk
            mock_chunk3 = MagicMock()
            mock_choice3 = MagicMock()
            mock_delta3 = MagicMock()
            mock_delta3.content = " help"
            mock_delta3.tool_calls = None
            mock_choice3.delta = mock_delta3
            mock_choice3.finish_reason = None
            mock_chunk3.choices = [mock_choice3]
            yield mock_chunk3

        pipeline = PipelineManager()
        pipeline.openai_client = AsyncMock()
        pipeline.openai_client.chat.completions.create = AsyncMock(return_value=mock_mixed_stream())
        pipeline._initialized = True

        session_id = await session_manager.create_session(
            persona_type="web_assistant",
            context={},
            auth_token="test_token"
        )

        try:
            collected_chunks: List[str] = []

            async for chunk in pipeline.generate_response(
                session_id=session_id,
                persona_type=PersonaType.WEB_ASSISTANT,
                user_message="Test mixed streaming",
                context={"user_id": "test_user"}
            ):
                collected_chunks.append(chunk)

            # Verify only text chunks collected (tool calls filtered)
            assert len(collected_chunks) >= 2, "Should receive text chunks"

            # Verify no tool call data in chunks
            full_content = "".join(collected_chunks)
            assert "call_123" not in full_content, "Tool call IDs should not appear in streamed text"

        finally:
            await session_manager.delete_session(session_id)


class TestStreamingEmptyChunks:
    """Tests for handling empty chunks during streaming"""

    async def test_streaming_handles_empty_chunks(self):
        """
        Test that pipeline handles empty chunks from OpenAI gracefully.

        Flow:
        1. Mock OpenAI to return mix of empty and non-empty chunks
        2. Generate response
        3. Verify empty chunks don't corrupt stream
        4. Verify only non-empty chunks delivered

        This tests:
        - Empty chunk filtering
        - Stream continuity
        - Real OpenAI behavior (sometimes sends empty deltas)
        """
        from pipeline_manager import PipelineManager
        from personas import PersonaType
        from session_manager import session_manager

        # Mock stream with empty chunks
        async def mock_stream_with_empties(*args, **kwargs):
            chunks_data = ["Hello", "", " ", "world", None, "!"]

            for chunk_text in chunks_data:
                mock_chunk = MagicMock()
                mock_choice = MagicMock()
                mock_delta = MagicMock()
                mock_delta.content = chunk_text
                mock_delta.tool_calls = None
                mock_choice.delta = mock_delta
                mock_choice.finish_reason = None
                mock_chunk.choices = [mock_choice]
                yield mock_chunk

        pipeline = PipelineManager()
        pipeline.openai_client = AsyncMock()
        pipeline.openai_client.chat.completions.create = AsyncMock(return_value=mock_stream_with_empties())
        pipeline._initialized = True

        session_id = await session_manager.create_session(
            persona_type="web_assistant",
            context={},
            auth_token="test_token"
        )

        try:
            collected_chunks: List[str] = []

            async for chunk in pipeline.generate_response(
                session_id=session_id,
                persona_type=PersonaType.WEB_ASSISTANT,
                user_message="Test empty chunks",
                context={"user_id": "test_user"}
            ):
                collected_chunks.append(chunk)

            # Verify non-empty chunks collected
            assert len(collected_chunks) > 0, "Should collect non-empty chunks"

            # Verify content makes sense (no corruption from empty chunks)
            full_content = "".join(collected_chunks)
            assert "Hello" in full_content, "Should contain first chunk"
            assert "world" in full_content, "Should contain second chunk"
            assert "!" in full_content, "Should contain third chunk"

        finally:
            await session_manager.delete_session(session_id)


class TestStreamingContentAccumulation:
    """Tests for full content accumulation during streaming"""

    async def test_full_content_accumulates_correctly(self):
        """
        Test that full_content accumulation matches chunk concatenation.

        Flow:
        1. Mock OpenAI to return known chunks
        2. Generate response
        3. Collect chunks individually
        4. Verify concatenation matches expected full content

        This tests:
        - Content accumulation logic
        - No data loss during streaming
        - Chunk + full_content consistency
        """
        from pipeline_manager import PipelineManager
        from personas import PersonaType
        from session_manager import session_manager

        test_chunks = ["The", " quick", " brown", " fox"]
        expected_full = "The quick brown fox"

        async def mock_stream(*args, **kwargs):
            for chunk_text in test_chunks:
                mock_chunk = MagicMock()
                mock_choice = MagicMock()
                mock_delta = MagicMock()
                mock_delta.content = chunk_text
                mock_delta.tool_calls = None
                mock_choice.delta = mock_delta
                mock_choice.finish_reason = None
                mock_chunk.choices = [mock_choice]
                yield mock_chunk

        pipeline = PipelineManager()
        pipeline.openai_client = AsyncMock()
        pipeline.openai_client.chat.completions.create = AsyncMock(return_value=mock_stream())
        pipeline._initialized = True

        session_id = await session_manager.create_session(
            persona_type="web_assistant",
            context={},
            auth_token="test_token"
        )

        try:
            collected_chunks: List[str] = []
            accumulated_content = ""

            async for chunk in pipeline.generate_response(
                session_id=session_id,
                persona_type=PersonaType.WEB_ASSISTANT,
                user_message="Test accumulation",
                context={"user_id": "test_user"}
            ):
                collected_chunks.append(chunk)
                accumulated_content += chunk

            # Verify chunk-by-chunk accumulation matches expected
            assert accumulated_content == expected_full, \
                f"Accumulated content should be '{expected_full}', got '{accumulated_content}'"

            # Verify collected chunks match original
            assert len(collected_chunks) == len(test_chunks), \
                f"Should collect {len(test_chunks)} chunks, got {len(collected_chunks)}"

            # Verify each chunk matches
            for i, expected in enumerate(test_chunks):
                assert collected_chunks[i] == expected, \
                    f"Chunk {i} should be '{expected}', got '{collected_chunks[i]}'"

        finally:
            await session_manager.delete_session(session_id)

    async def test_streaming_preserves_unicode_and_special_chars(self):
        """
        Test that streaming preserves Unicode and special characters.

        Flow:
        1. Mock OpenAI to return chunks with Unicode (emoji, accents) and special chars
        2. Generate response
        3. Verify characters preserved correctly

        This tests:
        - Unicode handling in streams
        - Special character preservation
        - Encoding correctness
        """
        from pipeline_manager import PipelineManager
        from personas import PersonaType
        from session_manager import session_manager

        # Chunks with Unicode and special chars
        test_chunks = ["Hello", " 👋", " café", " ñoño", " 中文", " 🎉"]

        async def mock_stream(*args, **kwargs):
            for chunk_text in test_chunks:
                mock_chunk = MagicMock()
                mock_choice = MagicMock()
                mock_delta = MagicMock()
                mock_delta.content = chunk_text
                mock_delta.tool_calls = None
                mock_choice.delta = mock_delta
                mock_choice.finish_reason = None
                mock_chunk.choices = [mock_choice]
                yield mock_chunk

        pipeline = PipelineManager()
        pipeline.openai_client = AsyncMock()
        pipeline.openai_client.chat.completions.create = AsyncMock(return_value=mock_stream())
        pipeline._initialized = True

        session_id = await session_manager.create_session(
            persona_type="web_assistant",
            context={},
            auth_token="test_token"
        )

        try:
            collected_chunks: List[str] = []

            async for chunk in pipeline.generate_response(
                session_id=session_id,
                persona_type=PersonaType.WEB_ASSISTANT,
                user_message="Test Unicode",
                context={"user_id": "test_user"}
            ):
                collected_chunks.append(chunk)

            full_content = "".join(collected_chunks)

            # Verify Unicode preserved
            assert "👋" in full_content, "Should preserve emoji"
            assert "café" in full_content, "Should preserve accented characters"
            assert "ñoño" in full_content, "Should preserve Spanish characters"
            assert "中文" in full_content, "Should preserve Chinese characters"
            assert "🎉" in full_content, "Should preserve emoji"

        finally:
            await session_manager.delete_session(session_id)
