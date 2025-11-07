"""
Pipeline testing utilities

Provides reusable mocks and helpers for testing pipeline functionality.
"""
from typing import List, Dict, Any, Optional
from unittest.mock import Mock, AsyncMock, MagicMock


class MockPipelineManager:
    """
    Simplified pipeline manager mock for testing

    Usage:
        pipeline = MockPipelineManager(
            responses=["Hello", " world", "!"],
            ui_actions=[{"action": "navigate", "path": "/clients/123"}]
        )

        async for chunk in pipeline.generate_response_with_chaining(...):
            print(chunk)

        actions = pipeline.pop_ui_actions()
    """

    def __init__(
        self,
        responses: Optional[List[str]] = None,
        ui_actions: Optional[List[Dict[str, Any]]] = None,
        should_fail: bool = False,
        failure_message: str = "Pipeline error"
    ):
        """
        Create a mock pipeline manager

        Args:
            responses: List of response chunks to yield
            ui_actions: List of UI actions to return from pop_ui_actions()
            should_fail: If True, raise exception during generation
            failure_message: Error message if should_fail=True
        """
        self.responses = responses or ["Test response"]
        self.ui_actions = ui_actions or []
        self.should_fail = should_fail
        self.failure_message = failure_message
        self.call_count = 0
        self.call_args_history: List[tuple] = []

    async def generate_response_with_chaining(
        self,
        session_id: str,
        user_message: str,
        **kwargs
    ):
        """Mock generate_response_with_chaining method"""
        self.call_count += 1
        self.call_args_history.append((session_id, user_message, kwargs))

        if self.should_fail:
            raise Exception(self.failure_message)

        for chunk in self.responses:
            yield chunk

    def pop_ui_actions(self) -> List[Dict[str, Any]]:
        """Mock pop_ui_actions method"""
        actions = self.ui_actions
        self.ui_actions = []
        return actions

    def reset(self):
        """Reset call tracking"""
        self.call_count = 0
        self.call_args_history = []


def create_mock_openai_response(
    content: str,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    finish_reason: str = "stop"
) -> Mock:
    """
    Create a mock OpenAI API response

    Args:
        content: Response content
        tool_calls: List of tool calls (if any)
        finish_reason: Finish reason (stop, tool_calls, length, etc.)

    Returns:
        Mock OpenAI response object
    """
    mock_message = MagicMock()
    mock_message.content = content
    mock_message.tool_calls = tool_calls
    mock_message.role = "assistant"

    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_choice.finish_reason = finish_reason

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = MagicMock()
    mock_response.usage.total_tokens = 100

    return mock_response


def create_mock_tool_call(
    tool_name: str,
    arguments: Dict[str, Any],
    tool_call_id: str = "call_123"
) -> Dict[str, Any]:
    """
    Create a mock tool call object

    Args:
        tool_name: Name of the tool
        arguments: Tool arguments
        tool_call_id: Tool call ID

    Returns:
        Tool call dictionary
    """
    import json
    return {
        "id": tool_call_id,
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": json.dumps(arguments)
        }
    }


def create_mock_openai_response_with_tool_call(
    tool_name: str,
    tool_args: Dict[str, Any],
    tool_call_id: str = "call_123"
) -> Mock:
    """
    Create a mock OpenAI response that includes a tool call

    Args:
        tool_name: Name of the tool to call
        tool_args: Arguments for the tool
        tool_call_id: Tool call ID

    Returns:
        Mock OpenAI response with tool call
    """
    tool_call = create_mock_tool_call(tool_name, tool_args, tool_call_id)

    mock_message = MagicMock()
    mock_message.content = None
    mock_message.tool_calls = [MagicMock(**{
        "id": tool_call["id"],
        "type": tool_call["type"],
        "function": MagicMock(**{
            "name": tool_call["function"]["name"],
            "arguments": tool_call["function"]["arguments"]
        })
    })]
    mock_message.role = "assistant"

    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_choice.finish_reason = "tool_calls"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = MagicMock()
    mock_response.usage.total_tokens = 100

    return mock_response


def create_streaming_mock_response(chunks: List[str]):
    """
    Create a mock for streaming OpenAI responses

    Args:
        chunks: List of text chunks to stream

    Returns:
        Async generator mock
    """
    async def mock_stream():
        for chunk in chunks:
            mock_chunk = MagicMock()
            mock_delta = MagicMock()
            mock_delta.content = chunk
            mock_choice = MagicMock()
            mock_choice.delta = mock_delta
            mock_chunk.choices = [mock_choice]
            yield mock_chunk

    return mock_stream()
