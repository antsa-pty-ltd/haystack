"""
Test Utilities for Common Patterns

Provides helper functions and decorators for common test scenarios
to reduce boilerplate and improve test clarity.

Features:
- Helper functions for common setup/teardown patterns
- Decorators for injecting common fixtures
- Assertion helpers for common validation patterns
"""

import asyncio
import functools
from typing import Callable, Any, Optional, Dict
from unittest.mock import AsyncMock, Mock, patch
import pytest


def create_mock_pipeline_context(
    persona_type: str = "web_assistant",
    auth_token: str = "test_token",
    profile_id: str = "test_profile",
    session_id: str = "test_session",
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a complete mock pipeline execution context.

    Common across most pipeline tests to avoid repetition.

    Args:
        persona_type: AI persona (default: web_assistant)
        auth_token: Authentication token
        profile_id: User profile ID
        session_id: Session ID
        context: Additional context (merged with defaults)

    Returns:
        Complete context dict for pipeline operations

    Example:
        ctx = create_mock_pipeline_context(
            persona_type="jaimee_therapist",
            context={"page_type": "transcribe_page"}
        )
        assert ctx["auth_token"] == "test_token"
        assert ctx["context"]["page_type"] == "transcribe_page"
    """
    default_context = {
        "persona_type": persona_type,
        "auth_token": auth_token,
        "profile_id": profile_id,
        "session_id": session_id,
        "context": context or {}
    }
    return default_context


def create_mock_http_responses(
    endpoints: Dict[str, Dict[str, Any]]
) -> AsyncMock:
    """
    Create a mock httpx.AsyncClient with predefined responses.

    Useful for mocking NestJS API calls in tool execution.

    Args:
        endpoints: Dict mapping endpoint patterns to response configs
                  Example: {
                      "/clients/search": {"data": {"clients": []}, "status": 200},
                      "/sessions/123": {"data": {"id": "123"}, "status": 200},
                      "/invalid": {"data": {"error": "Not found"}, "status": 404}
                  }

    Returns:
        AsyncMock httpx client that responds based on endpoint

    Example:
        mock_client = create_mock_http_responses({
            "/clients/search": {"data": {"clients": [...]}, "status": 200},
            "/errors": {"data": {}, "status": 500}
        })
        response = await mock_client.get("/clients/search")
        assert response.status_code == 200
    """
    async def mock_request(method, url, **kwargs):
        response = AsyncMock()

        # Find matching endpoint
        for pattern, config in endpoints.items():
            if pattern in url or url.endswith(pattern):
                response.status_code = config.get("status", 200)
                response.json = AsyncMock(return_value=config.get("data", {}))
                response.text = str(config.get("data", {}))
                return response

        # Default 404
        response.status_code = 404
        response.json = AsyncMock(return_value={"error": "Not found"})
        return response

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=lambda url, **kwargs: mock_request("GET", url, **kwargs))
    mock_client.post = AsyncMock(side_effect=lambda url, **kwargs: mock_request("POST", url, **kwargs))
    mock_client.put = AsyncMock(side_effect=lambda url, **kwargs: mock_request("PUT", url, **kwargs))
    mock_client.delete = AsyncMock(side_effect=lambda url, **kwargs: mock_request("DELETE", url, **kwargs))

    return mock_client


def with_mock_pipeline(
    persona_type: str = "web_assistant",
    auth_token: str = "test_token",
    profile_id: str = "test_profile"
) -> Callable:
    """
    Decorator to inject a mocked pipeline into test methods.

    Reduces boilerplate for pipeline setup in multiple tests.

    Args:
        persona_type: AI persona type
        auth_token: Authentication token
        profile_id: User profile ID

    Returns:
        Decorator function

    Example:
        @with_mock_pipeline("web_assistant")
        async def test_my_scenario(mock_pipeline):
            # mock_pipeline is already created and initialized
            mock_pipeline.openai_client = AsyncMock(...)
            # Test logic here
    """
    def decorator(test_func: Callable) -> Callable:
        @functools.wraps(test_func)
        async def wrapper(*args, **kwargs):
            from pipeline_manager import PipelineManager
            from session_manager import session_manager

            # Create session
            session_id = await session_manager.create_session(
                persona_type=persona_type,
                auth_token=auth_token,
                profile_id=profile_id
            )

            try:
                # Initialize pipeline
                pipeline = PipelineManager()
                await pipeline.initialize()

                # Inject pipeline into test
                kwargs['mock_pipeline'] = pipeline
                kwargs['session_id'] = session_id

                # Run test
                return await test_func(*args, **kwargs)
            finally:
                # Cleanup
                await session_manager.delete_session(session_id)

        return wrapper
    return decorator


def with_mock_session(
    persona_type: str = "web_assistant",
    auth_token: str = "test_token",
    profile_id: str = "test_profile"
) -> Callable:
    """
    Decorator to inject a mock session into test methods.

    Simpler than with_mock_pipeline if only session is needed.

    Args:
        persona_type: AI persona type
        auth_token: Authentication token
        profile_id: User profile ID

    Returns:
        Decorator function

    Example:
        @with_mock_session("jaimee_therapist")
        async def test_session_behavior(session_id):
            # session_id is already created
            from session_manager import session_manager
            session = await session_manager.get_session(session_id)
            assert session is not None
    """
    def decorator(test_func: Callable) -> Callable:
        @functools.wraps(test_func)
        async def wrapper(*args, **kwargs):
            from session_manager import session_manager

            # Create session
            session_id = await session_manager.create_session(
                persona_type=persona_type,
                auth_token=auth_token,
                profile_id=profile_id
            )

            try:
                # Inject session_id into test
                kwargs['session_id'] = session_id

                # Run test
                return await test_func(*args, **kwargs)
            finally:
                # Cleanup
                await session_manager.delete_session(session_id)

        return wrapper
    return decorator


def assert_tool_call_sequence(
    actual_calls: list,
    expected_tools: list
) -> None:
    """
    Assert that tools were called in expected order.

    Useful for validating tool chains execute correctly.

    Args:
        actual_calls: List of actual tool calls (from mock.call_args_list)
        expected_tools: List of expected tool names in order

    Raises:
        AssertionError if sequence doesn't match

    Example:
        # Mock tool manager call
        tool_manager = AsyncMock()
        await tool_manager.execute_tool("search_clients", {"query": "John"})
        await tool_manager.execute_tool("get_client_summary", {"client_id": "123"})

        assert_tool_call_sequence(
            tool_manager.execute_tool.call_args_list,
            ["search_clients", "get_client_summary"]
        )
    """
    actual_tool_names = []

    for call in actual_calls:
        # Extract tool name from call args
        # Handles different call signatures
        if call.args and len(call.args) > 0:
            tool_name = call.args[0]
        elif "tool_name" in call.kwargs:
            tool_name = call.kwargs["tool_name"]
        else:
            continue

        actual_tool_names.append(tool_name)

    assert actual_tool_names == expected_tools, (
        f"Tool sequence mismatch.\n"
        f"Expected: {expected_tools}\n"
        f"Actual: {actual_tool_names}"
    )


def assert_api_calls_made(
    mock_client: AsyncMock,
    expected_endpoints: Dict[str, Dict[str, Any]]
) -> None:
    """
    Assert that specific API calls were made with expected parameters.

    Useful for validating NestJS API interactions.

    Args:
        mock_client: Mock httpx client
        expected_endpoints: Dict mapping endpoints to expected call info
                           Example: {
                               "/clients/search": {"method": "get", "params": {...}},
                               "/sessions/123": {"method": "put"}
                           }

    Raises:
        AssertionError if expected calls weren't made

    Example:
        tool_manager.http_client = mock_client
        # ... tool execution ...

        assert_api_calls_made(
            mock_client,
            {
                "/clients/search": {"method": "get"}
            }
        )
    """
    all_calls = []

    # Collect all calls from mock client
    for method_name in ["get", "post", "put", "delete"]:
        mock_method = getattr(mock_client, method_name)
        if mock_method.called:
            for call in mock_method.call_args_list:
                all_calls.append({
                    "method": method_name.upper(),
                    "endpoint": call.args[0] if call.args else None
                })

    # Validate each expected endpoint was called
    for endpoint, expected_info in expected_endpoints.items():
        expected_method = expected_info.get("method", "get").upper()
        found = False

        for actual_call in all_calls:
            if endpoint in actual_call["endpoint"] and actual_call["method"] == expected_method:
                found = True
                break

        assert found, (
            f"Expected API call not made: {expected_method} {endpoint}\n"
            f"Actual calls: {all_calls}"
        )


async def async_timeout(coro, timeout_seconds: float = 5.0) -> Any:
    """
    Helper to run async test with timeout protection.

    Prevents hanging tests from blocking test suite.

    Args:
        coro: Coroutine to run
        timeout_seconds: Timeout in seconds (default 5)

    Returns:
        Coroutine result

    Raises:
        asyncio.TimeoutError if timeout exceeded

    Example:
        result = await async_timeout(
            pipeline.generate_response(...),
            timeout_seconds=10.0
        )
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        raise asyncio.TimeoutError(
            f"Test operation timed out after {timeout_seconds} seconds"
        )


def create_mock_redis_cache() -> AsyncMock:
    """
    Create a mock Redis cache for session/state tests.

    Simulates Redis behavior without requiring actual Redis.

    Returns:
        AsyncMock configured as Redis client

    Example:
        mock_redis = create_mock_redis_cache()
        await mock_redis.set("key", "value")
        value = await mock_redis.get("key")
        assert value == "value"
    """
    mock_redis = AsyncMock()
    data_store = {}

    async def mock_set(key, value, **kwargs):
        data_store[key] = value
        return True

    async def mock_get(key):
        return data_store.get(key)

    async def mock_delete(key):
        if key in data_store:
            del data_store[key]
            return 1
        return 0

    async def mock_exists(key):
        return 1 if key in data_store else 0

    mock_redis.set = AsyncMock(side_effect=mock_set)
    mock_redis.get = AsyncMock(side_effect=mock_get)
    mock_redis.delete = AsyncMock(side_effect=mock_delete)
    mock_redis.exists = AsyncMock(side_effect=mock_exists)

    return mock_redis
