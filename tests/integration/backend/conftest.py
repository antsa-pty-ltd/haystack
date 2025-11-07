"""
Pytest configuration and shared fixtures for backend integration tests.
"""

import os
import sys
# Add haystack directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

import pytest
import pytest_asyncio
from httpx import AsyncClient
import logging
import asyncio
from openai import APIError, RateLimitError, APIConnectionError, InternalServerError

# Configure logging for fixture messages
logger = logging.getLogger(__name__)


async def retry_on_transient_error(coro_func, max_retries=3):
    """
    Retry async function on transient errors with exponential backoff.

    Args:
        coro_func: Async function to retry
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        Result of the async function

    Raises:
        RateLimitError: If rate limit persists after all retries
        Exception: If non-transient error occurs
    """
    wait_times = [2, 4, 8]  # Exponential backoff: 2s, 4s, 8s

    for attempt in range(max_retries):
        try:
            return await coro_func()
        except (APIConnectionError, InternalServerError) as e:
            if attempt == max_retries - 1:
                raise
            wait_time = wait_times[attempt]
            logger.warning(
                f"Transient error on attempt {attempt + 1}/{max_retries}: {e}. "
                f"Retrying in {wait_time}s..."
            )
            await asyncio.sleep(wait_time)
        except RateLimitError as e:
            pytest.skip(f"OpenAI rate limit exceeded: {e}")

    raise Exception(f"Failed after {max_retries} retries")


@pytest_asyncio.fixture
async def async_client():
    """
    Provides an httpx AsyncClient configured for the FastAPI app.

    Usage in tests:
        async def test_something(async_client):
            response = await async_client.post("/endpoint", json={...})
            assert response.status_code == 200
    """
    from main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_openai():
    """
    Provides a mock OpenAI client for tests that need to mock OpenAI calls.

    Usage in tests:
        def test_something(mock_openai):
            # mock_openai is already configured as a Mock object
            # Configure its behavior as needed
            pass
    """
    from unittest.mock import Mock, AsyncMock

    mock = Mock()
    mock.chat.completions.create = AsyncMock()
    return mock


@pytest_asyncio.fixture
async def real_openai_client():
    """
    Provides a real OpenAI client for integration tests using actual OpenAI API.

    This fixture:
    - Checks for OPENAI_API_KEY environment variable
    - Skips the test with a clear message if the key is not set
    - Returns a real OpenAI() client if the key exists
    - Tracks token usage for cost estimation

    Usage in tests:
        def test_with_real_openai(real_openai_client):
            # Use the real OpenAI client
            response = await real_openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Hello"}]
            )
            assert response.choices[0].message.content

    Cost Tracking:
    - Token usage is logged during test execution
    - Approximate costs are calculated based on OpenAI pricing
    - Summary is printed after test completes

    Environment:
    - Requires: OPENAI_API_KEY environment variable
    - Skip Message: "OPENAI_API_KEY environment variable not set. Set it to run real OpenAI integration tests."
    """
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not openai_api_key:
        pytest.skip(
            "OPENAI_API_KEY environment variable not set. "
            "Set it to run real OpenAI integration tests."
        )

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=openai_api_key)

    # Validate API key works
    try:
        await client.models.list()
    except Exception as e:
        pytest.skip(
            f"OPENAI_API_KEY validation failed: {e}. "
            "Check that your API key is valid and has proper permissions."
        )

    # Initialize cost tracking
    client._test_token_usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
    }

    # Pricing per 1K tokens (as of latest OpenAI pricing)
    # These are approximate and should be verified against current OpenAI pricing
    pricing = {
        "gpt-4o": {
            "prompt": 0.0025,
            "completion": 0.01,
        },
        "gpt-4o-mini": {
            "prompt": 0.00015,
            "completion": 0.0006,
        },
        "gpt-4": {
            "prompt": 0.03,
            "completion": 0.06,
        },
        "gpt-4-turbo": {
            "prompt": 0.01,
            "completion": 0.03,
        },
        "gpt-3.5-turbo": {
            "prompt": 0.0005,
            "completion": 0.0015,
        },
    }

    def _track_usage(response, model: str = "gpt-4o-mini"):
        """Track token usage and estimate cost"""
        if hasattr(response, "usage"):
            usage = response.usage
            client._test_token_usage["prompt_tokens"] += usage.prompt_tokens
            client._test_token_usage["completion_tokens"] += usage.completion_tokens
            client._test_token_usage["total_tokens"] += usage.total_tokens

            # Calculate cost based on model
            model_pricing = pricing.get(model, pricing["gpt-4o-mini"])
            prompt_cost = (usage.prompt_tokens / 1000) * model_pricing["prompt"]
            completion_cost = (usage.completion_tokens / 1000) * model_pricing["completion"]
            total_cost = prompt_cost + completion_cost

            client._test_token_usage["estimated_cost_usd"] += total_cost

            logger.info(
                f"OpenAI API Call - Model: {model}, "
                f"Prompt Tokens: {usage.prompt_tokens}, "
                f"Completion Tokens: {usage.completion_tokens}, "
                f"Est. Cost: ${total_cost:.6f}"
            )

    # Attach tracking function to client
    client._track_usage = _track_usage

    yield client

    # Log final summary
    if client._test_token_usage["total_tokens"] > 0:
        logger.info(
            f"Real OpenAI Test Summary - "
            f"Total Tokens: {client._test_token_usage['total_tokens']}, "
            f"Estimated Total Cost: ${client._test_token_usage['estimated_cost_usd']:.6f}"
        )

    # Clean up async client connections
    try:
        await client.close()
    except Exception as e:
        logger.warning(f"Error closing OpenAI client: {e}")
