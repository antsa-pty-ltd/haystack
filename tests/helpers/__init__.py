"""
Test helper modules for Haystack integration tests

This package contains reusable test utilities to reduce code duplication
and improve test clarity.

Modules:
- mock_helpers: Mock builders for OpenAI, NestJS API, etc.
- test_utilities: Common helper functions and decorators
- websocket_helpers: WebSocket testing utilities
- pipeline_helpers: Pipeline mocking utilities
- session_helpers: Session factory for tests
- test_data_factory: Test data creation factories
"""

from .websocket_helpers import MockWebSocket, extract_messages_by_type
from .pipeline_helpers import MockPipelineManager
from .contract_helpers import assert_api_request, assert_api_response
from .session_helpers import SessionFactory
from .mock_helpers import (
    MockOpenAIBuilder,
    MockNestJSAPIBuilder,
    MockPolicyResponseBuilder,
    create_mock_streaming_response,
    create_httpx_mock_response,
    create_simple_tool_chain_mock
)
from .test_utilities import (
    create_mock_pipeline_context,
    create_mock_http_responses,
    with_mock_pipeline,
    with_mock_session,
    assert_tool_call_sequence,
    assert_api_calls_made,
    async_timeout,
    create_mock_redis_cache
)
from .test_data_factory import TestDataFactory

__all__ = [
    'MockWebSocket',
    'extract_messages_by_type',
    'MockPipelineManager',
    'assert_api_request',
    'assert_api_response',
    'SessionFactory',
    'MockOpenAIBuilder',
    'MockNestJSAPIBuilder',
    'MockPolicyResponseBuilder',
    'create_mock_streaming_response',
    'create_httpx_mock_response',
    'create_simple_tool_chain_mock',
    'create_mock_pipeline_context',
    'create_mock_http_responses',
    'with_mock_pipeline',
    'with_mock_session',
    'assert_tool_call_sequence',
    'assert_api_calls_made',
    'async_timeout',
    'create_mock_redis_cache',
    'TestDataFactory',
]
