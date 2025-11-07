"""
API contract validation helpers

Utilities for validating API request/response contracts in tests.
"""
from typing import Dict, Any, Optional, List
from unittest.mock import AsyncMock, MagicMock


def assert_api_request(
    mock_call: Any,
    expected_method: str,
    expected_endpoint: str,
    expected_params: Optional[Dict[str, Any]] = None,
    expected_headers: Optional[Dict[str, str]] = None,
    expected_json: Optional[Dict[str, Any]] = None
):
    """
    Assert that an API request matches expected contract

    Args:
        mock_call: Mock object that was called
        expected_method: Expected HTTP method (GET, POST, etc.)
        expected_endpoint: Expected endpoint path (substring match)
        expected_params: Expected query parameters
        expected_headers: Expected headers (partial match)
        expected_json: Expected JSON body

    Raises:
        AssertionError: If contract doesn't match
    """
    assert mock_call.called, "API request should have been made"

    call_args = mock_call.call_args

    # Check method
    if call_args[0]:  # Positional args
        actual_method = call_args[0][0] if len(call_args[0]) > 0 else None
        if actual_method:
            assert actual_method == expected_method, \
                f"Expected method {expected_method}, got {actual_method}"

    # Check endpoint
    if len(call_args[0]) > 1:
        actual_endpoint = call_args[0][1]
        assert expected_endpoint in actual_endpoint, \
            f"Expected endpoint containing '{expected_endpoint}', got '{actual_endpoint}'"

    # Check params
    if expected_params:
        actual_params = call_args.kwargs.get('params', {})
        for key, value in expected_params.items():
            assert key in actual_params, \
                f"Expected param '{key}' not found. Available: {list(actual_params.keys())}"
            assert actual_params[key] == value, \
                f"Expected param '{key}'={value}, got {actual_params[key]}"

    # Check headers
    if expected_headers:
        actual_headers = call_args.kwargs.get('headers', {})
        for key, value in expected_headers.items():
            assert key in actual_headers, \
                f"Expected header '{key}' not found. Available: {list(actual_headers.keys())}"
            assert actual_headers[key] == value, \
                f"Expected header '{key}'={value}, got {actual_headers[key]}"

    # Check JSON body
    if expected_json:
        actual_json = call_args.kwargs.get('json', {})
        for key, value in expected_json.items():
            assert key in actual_json, \
                f"Expected JSON field '{key}' not found. Available: {list(actual_json.keys())}"
            assert actual_json[key] == value, \
                f"Expected JSON field '{key}'={value}, got {actual_json[key]}"


def assert_api_response(
    result: Dict[str, Any],
    expected_success: bool = True,
    expected_fields: Optional[List[str]] = None,
    expected_result_type: Optional[type] = None,
    expected_error_contains: Optional[str] = None
):
    """
    Assert that an API response matches expected structure

    Args:
        result: The result dictionary from tool execution
        expected_success: Expected value of 'success' field
        expected_fields: List of fields that should exist in result['result']
        expected_result_type: Expected type of result['result']
        expected_error_contains: If error expected, substring to check for

    Raises:
        AssertionError: If response doesn't match expectations
    """
    assert result is not None, "Result should not be None"
    assert "success" in result, "Result should have 'success' field"
    assert result["success"] == expected_success, \
        f"Expected success={expected_success}, got {result['success']}"

    if expected_success:
        assert "result" in result, "Successful result should have 'result' field"

        # Check result type
        if expected_result_type:
            assert isinstance(result["result"], expected_result_type), \
                f"Expected result type {expected_result_type}, got {type(result['result'])}"

        # Check expected fields
        if expected_fields and isinstance(result["result"], dict):
            for field in expected_fields:
                assert field in result["result"], \
                    f"Expected field '{field}' not found in result. " \
                    f"Available: {list(result['result'].keys())}"
    else:
        # Error case
        if expected_error_contains:
            error_msg = str(result.get("error", result.get("message", "")))
            assert expected_error_contains.lower() in error_msg.lower(), \
                f"Expected error containing '{expected_error_contains}', got '{error_msg}'"


def create_mock_http_client(
    get_responses: Optional[Dict[str, Any]] = None,
    post_responses: Optional[Dict[str, Any]] = None,
    default_status: int = 200
) -> AsyncMock:
    """
    Create a mock HTTP client with configurable responses

    Args:
        get_responses: Dict mapping URL substrings to response data
        post_responses: Dict mapping URL substrings to response data
        default_status: Default HTTP status code

    Returns:
        Mock HTTP client instance

    Usage:
        mock_client = create_mock_http_client(
            get_responses={
                "clients": {"clients": [...]},
                "sessions": {"sessions": [...]}
            }
        )
    """
    get_responses = get_responses or {}
    post_responses = post_responses or {}

    def create_response(status_code, data):
        """Create a mock response object"""
        response = MagicMock()
        response.status_code = status_code
        response.json = MagicMock(return_value=data)
        response.text = str(data)
        return response

    async def mock_get(url, **kwargs):
        """Mock GET request"""
        for key, data in get_responses.items():
            if key in url:
                return create_response(default_status, data)
        return create_response(default_status, {})

    async def mock_post(url, **kwargs):
        """Mock POST request"""
        for key, data in post_responses.items():
            if key in url:
                return create_response(default_status, data)
        return create_response(default_status, {})

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=mock_get)
    mock_client.post = AsyncMock(side_effect=mock_post)
    mock_client.headers = {}

    return mock_client


def create_mock_nestjs_api_with_auth(
    authorized: bool = True,
    responses: Optional[Dict[str, Any]] = None
) -> AsyncMock:
    """
    Create a mock NestJS API client that validates auth

    Args:
        authorized: If True, accepts requests with auth. If False, returns 401
        responses: Dict mapping endpoint substrings to response data

    Returns:
        Mock HTTP client that validates Authorization header

    Usage:
        mock_api = create_mock_nestjs_api_with_auth(
            authorized=True,
            responses={"clients": {"clients": [...]}}
        )
    """
    responses = responses or {}

    def create_response(status_code, data):
        response = MagicMock()
        response.status_code = status_code
        response.json = MagicMock(return_value=data)
        response.text = str(data)
        return response

    async def request_with_auth_check(method, url, **kwargs):
        """Check auth header before processing"""
        headers = kwargs.get('headers', {})

        if not authorized or 'Authorization' not in headers:
            return create_response(401, {"error": "Unauthorized"})

        # Find matching response
        for key, data in responses.items():
            if key in url:
                return create_response(200, data)

        return create_response(200, {})

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=lambda url, **kw: request_with_auth_check('GET', url, **kw))
    mock_client.post = AsyncMock(side_effect=lambda url, **kw: request_with_auth_check('POST', url, **kw))
    mock_client.headers = {}

    return mock_client
