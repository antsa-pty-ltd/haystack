"""
Mock Helper Utilities

Provides builder classes and utilities to simplify mocking in tests.

Key Features:
- MockOpenAIBuilder: Chain-based builder for OpenAI responses with error support
- MockNestJSAPIBuilder: HTTP endpoint mocking for NestJS API interactions
- MockPolicyResponseBuilder: Policy violation response mocking
- create_httpx_mock_response: Create proper httpx Response objects
- create_simple_tool_chain_mock: Simple 2-3 tool chain mocking
- Streaming response utilities

Architecture:
- Uses unittest.mock for all mocking (not httpx._mock)
- Supports both async and sync contexts
- Provides sensible defaults for common scenarios
"""

import json
from unittest.mock import Mock, AsyncMock
from typing import List, Dict, Any, Optional, Tuple
import httpx


class MockOpenAIBuilder:
    """
    Builder for creating OpenAI mock responses.

    Supports:
    - Single and multiple tool calls
    - Text responses
    - Error simulation (timeout, rate limit, validation error)
    - Response sequencing (different response per call)
    """

    def __init__(self):
        self.responses = []
        self.call_index = 0
        self.error_on_call = None
        self.error_type = None
        self.error_message = None

    def add_tool_call(self, tool_name: str, arguments: dict, call_id: Optional[str] = None) -> 'MockOpenAIBuilder':
        """
        Add a tool call response.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments as dict
            call_id: Optional call ID (auto-generated if not provided)

        Returns:
            Self for chaining
        """
        if call_id is None:
            call_id = f"call_{len(self.responses) + 1}"

        self.responses.append({
            "tool_calls": [{
                "id": call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(arguments)
                }
            }]
        })
        return self

    def add_multiple_tool_calls(self, tool_calls: List[tuple]) -> 'MockOpenAIBuilder':
        """
        Add multiple tool calls in one response.

        Args:
            tool_calls: List of (tool_name, arguments) tuples
        """
        calls = []
        for idx, (tool_name, arguments) in enumerate(tool_calls):
            calls.append({
                "id": f"call_{len(self.responses) + 1}_{idx}",
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(arguments)
                }
            })

        self.responses.append({"tool_calls": calls})
        return self

    def add_text_response(self, content: str) -> 'MockOpenAIBuilder':
        """
        Add a text response (no tool calls).

        Args:
            content: Response text content

        Returns:
            Self for chaining
        """
        self.responses.append({
            "tool_calls": None,
            "content": content
        })
        return self

    def add_timeout_error(self) -> 'MockOpenAIBuilder':
        """
        Add a timeout error response (simulates OpenAI timeout).

        Returns:
            Self for chaining
        """
        self.responses.append({
            "error": "timeout",
            "error_message": "Request to OpenAI API timed out"
        })
        return self

    def add_rate_limit_error(self) -> 'MockOpenAIBuilder':
        """
        Add a rate limit error response.

        Returns:
            Self for chaining
        """
        self.responses.append({
            "error": "rate_limit",
            "error_message": "Rate limit exceeded"
        })
        return self

    def add_validation_error(self, message: str = "Invalid request") -> 'MockOpenAIBuilder':
        """
        Add a validation error response.

        Args:
            message: Error message

        Returns:
            Self for chaining
        """
        self.responses.append({
            "error": "validation",
            "error_message": message
        })
        return self

    def build(self) -> AsyncMock:
        """
        Build the mock OpenAI client.

        Returns:
            AsyncMock configured with the response sequence
        """
        mock_openai = Mock()
        call_index = [0]  # Use list to maintain state

        async def mock_chat_completion(*args, **kwargs):
            """Mock chat completion that returns responses in sequence"""
            current_index = call_index[0]
            call_index[0] += 1

            # Check if streaming is enabled
            is_streaming = kwargs.get('stream', False)

            # Safety: return final response if we exceed sequence
            if current_index >= len(self.responses):
                if is_streaming:
                    async def default_stream():
                        chunk = Mock()
                        chunk.choices = [Mock()]
                        chunk.choices[0].delta = Mock()
                        chunk.choices[0].delta.content = "Done"
                        chunk.choices[0].delta.tool_calls = None
                        yield chunk
                    return default_stream()
                else:
                    response = Mock()
                    response.choices = [Mock()]
                    response.choices[0].message = Mock()
                    response.choices[0].message.content = "Done"
                    response.choices[0].message.tool_calls = None
                    response.choices[0].finish_reason = "stop"
                    return response

            current_response = self.responses[current_index]

            # Handle errors
            if current_response.get("error"):
                error_type = current_response.get("error")
                error_msg = current_response.get("error_message", "Unknown error")

                if error_type == "timeout":
                    raise TimeoutError(error_msg)
                elif error_type == "rate_limit":
                    from openai import RateLimitError
                    raise RateLimitError(error_msg)
                elif error_type == "validation":
                    raise ValueError(error_msg)
                else:
                    raise Exception(error_msg)

            # Handle streaming mode
            if is_streaming:
                async def stream_response():
                    """Generate streaming chunks for current response"""
                    if current_response.get("tool_calls"):
                        # Stream tool calls
                        for idx, tc in enumerate(current_response["tool_calls"]):
                            # First chunk with tool call metadata
                            chunk = Mock()
                            chunk.choices = [Mock()]
                            chunk.choices[0].delta = Mock()
                            chunk.choices[0].delta.content = None
                            chunk.choices[0].delta.tool_calls = [Mock()]
                            chunk.choices[0].delta.tool_calls[0].index = idx
                            chunk.choices[0].delta.tool_calls[0].id = tc["id"]
                            chunk.choices[0].delta.tool_calls[0].type = tc["type"]
                            chunk.choices[0].delta.tool_calls[0].function = Mock()
                            chunk.choices[0].delta.tool_calls[0].function.name = tc["function"]["name"]
                            chunk.choices[0].delta.tool_calls[0].function.arguments = tc["function"]["arguments"]
                            yield chunk
                    else:
                        # Stream text response
                        content = current_response.get("content", "Done")
                        # Split content into chunks for realistic streaming
                        chunk_size = max(1, len(content) // 3) if len(content) > 3 else 1
                        for i in range(0, len(content), chunk_size):
                            chunk = Mock()
                            chunk.choices = [Mock()]
                            chunk.choices[0].delta = Mock()
                            chunk.choices[0].delta.content = content[i:i+chunk_size]
                            chunk.choices[0].delta.tool_calls = None
                            yield chunk

                return stream_response()

            # Non-streaming mode (original behavior)
            response = Mock()
            response.choices = [Mock()]
            response.choices[0].message = Mock()

            if current_response.get("tool_calls"):
                # Build tool call mocks
                response.choices[0].message.tool_calls = []
                for tc in current_response["tool_calls"]:
                    mock_tool_call = Mock()
                    mock_tool_call.id = tc["id"]
                    mock_tool_call.type = tc["type"]
                    mock_tool_call.function = Mock()
                    mock_tool_call.function.name = tc["function"]["name"]
                    mock_tool_call.function.arguments = tc["function"]["arguments"]
                    response.choices[0].message.tool_calls.append(mock_tool_call)
                response.choices[0].message.content = None
            else:
                # Text response
                response.choices[0].message.content = current_response.get("content", "Done")
                response.choices[0].message.tool_calls = None

            response.choices[0].finish_reason = "stop"
            return response

        mock_openai.chat = Mock()
        mock_openai.chat.completions = Mock()
        mock_openai.chat.completions.create = AsyncMock(side_effect=mock_chat_completion)

        return mock_openai


class MockNestJSAPIBuilder:
    """Builder for creating NestJS API mock responses"""

    def __init__(self):
        self.endpoint_responses = {}
        self.default_response = {"success": True}

    def add_endpoint(
        self,
        pattern: str,
        response_data: dict,
        status_code: int = 200
    ) -> 'MockNestJSAPIBuilder':
        """
        Add a mock response for an endpoint pattern.

        Args:
            pattern: URL pattern to match (e.g., '/clients/search')
            response_data: JSON response data
            status_code: HTTP status code
        """
        self.endpoint_responses[pattern] = {
            "data": response_data,
            "status": status_code
        }
        return self

    def set_default_response(self, response_data: dict, status_code: int = 200) -> 'MockNestJSAPIBuilder':
        """
        Set default response for unmatched endpoints.

        Args:
            response_data: Default JSON response
            status_code: Default HTTP status code
        """
        self.default_response = {"data": response_data, "status": status_code}
        return self

    def build(self) -> AsyncMock:
        """
        Build the mock httpx.AsyncClient.

        Returns:
            AsyncMock configured with endpoint responses
        """
        async def mock_request(url, **kwargs):
            """Mock HTTP request handler"""
            response = AsyncMock()

            # Find matching endpoint
            for pattern, config in self.endpoint_responses.items():
                if pattern in url:
                    response.status_code = config["status"]
                    response.json = AsyncMock(return_value=config["data"])
                    return response

            # Use default response
            response.status_code = self.default_response.get("status", 200)
            response.json = AsyncMock(return_value=self.default_response.get("data", {}))
            return response

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=mock_request)
        mock_client.post = AsyncMock(side_effect=mock_request)
        mock_client.put = AsyncMock(side_effect=mock_request)
        mock_client.delete = AsyncMock(side_effect=mock_request)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        return mock_client


class MockPolicyResponseBuilder:
    """Builder for creating policy check mock responses"""

    def __init__(self):
        self.is_violation = False
        self.violation_type = None
        self.reason = ""
        self.confidence = "low"

    def with_violation(
        self,
        violation_type: str = "medical_diagnosis_request",
        reason: str = "Template requests medical diagnosis",
        confidence: str = "high"
    ) -> 'MockPolicyResponseBuilder':
        """
        Create a violation response.

        Args:
            violation_type: Type of violation
            reason: Reason for violation
            confidence: Confidence level (high/medium/low)
        """
        self.is_violation = True
        self.violation_type = violation_type
        self.reason = reason
        self.confidence = confidence
        return self

    def without_violation(self) -> 'MockPolicyResponseBuilder':
        """Create a non-violation response"""
        self.is_violation = False
        self.violation_type = None
        self.reason = ""
        self.confidence = "low"
        return self

    def build(self) -> Mock:
        """
        Build the mock policy response.

        Returns:
            Mock response from OpenAI policy check
        """
        response = Mock()
        response.choices = [Mock()]
        response.choices[0].message = Mock()
        response.choices[0].message.content = json.dumps({
            "is_violation": self.is_violation,
            "violation_type": self.violation_type,
            "reason": self.reason,
            "confidence": self.confidence
        })
        response.choices[0].finish_reason = "stop"
        return response


def create_httpx_mock_response(
    status_code: int = 200,
    json_data: Optional[Dict[str, Any]] = None,
    text: str = ""
) -> AsyncMock:
    """
    Create a proper httpx mock response for testing tool HTTP calls.

    Since tools use httpx (not aiohttp), this helper creates realistic
    response mocks that match httpx.Response interface.

    Args:
        status_code: HTTP status code (default 200)
        json_data: JSON response body (optional)
        text: Text response body (optional)

    Returns:
        AsyncMock that behaves like httpx.Response

    Example:
        response = create_httpx_mock_response(
            status_code=200,
            json_data={"id": "client-123", "name": "John Doe"}
        )
        assert response.status_code == 200
        assert await response.json() == {"id": "client-123", "name": "John Doe"}
    """
    mock_response = AsyncMock()
    mock_response.status_code = status_code
    mock_response.text = text
    mock_response.json = AsyncMock(return_value=json_data or {})
    mock_response.is_success = status_code < 400
    mock_response.is_error = status_code >= 400
    return mock_response


def create_simple_tool_chain_mock(
    tool_calls: List[Tuple[str, Dict[str, Any]]]
) -> Mock:
    """
    Create a mock OpenAI client for simple 2-3 tool chains.

    This helper simplifies the common pattern of testing tool chains
    without complex setup. Each tuple is (tool_name, arguments).

    Args:
        tool_calls: List of (tool_name, arguments) tuples to execute sequentially

    Returns:
        Mock OpenAI client configured for the tool chain

    Example:
        mock_openai = create_simple_tool_chain_mock([
            ("search_clients", {"query": "John"}),
            ("get_client_summary", {"client_id": "123"}),
            ("get_conversations", {"client_id": "123"})
        ])

        # Then use final text response
        mock_openai.chat.completions.create = AsyncMock(...)  # if needed
    """
    builder = MockOpenAIBuilder()

    # Add tool calls
    for tool_name, arguments in tool_calls:
        builder.add_tool_call(tool_name, arguments)

    # Add final text response to conclude chain
    builder.add_text_response("Tool chain completed successfully")

    return builder.build()


def create_mock_streaming_response(chunks: List[str]) -> AsyncMock:
    """
    Create a mock streaming response for OpenAI.

    Args:
        chunks: List of content chunks to stream

    Returns:
        AsyncMock that yields chunks
    """
    async def mock_stream(*args, **kwargs):
        """Mock streaming generator"""
        for chunk_content in chunks:
            chunk = Mock()
            chunk.choices = [Mock()]
            chunk.choices[0].delta = Mock()
            chunk.choices[0].delta.content = chunk_content
            chunk.choices[0].delta.tool_calls = None
            yield chunk

    mock = AsyncMock()
    mock.chat = Mock()
    mock.chat.completions = Mock()
    mock.chat.completions.create = Mock(return_value=mock_stream())
    return mock
