"""
Rate Limiting Simple Tests

Simplified tests that focus on verifying rate limiting infrastructure
without complex AsyncGenerator mocking.
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

import pytest
import asyncio

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class TestRateLimitingInfrastructure:
    """Tests for rate limiting infrastructure"""

    async def test_user_semaphore_created_with_correct_limit(self):
        """
        Test that user semaphores are created with limit of 10.

        This is the simple version that verifies the infrastructure exists.
        """
        from pipeline_manager import PipelineManager

        pipeline = PipelineManager()
        await pipeline.initialize()

        # Get semaphore for a user
        user_id = "test_user_1"
        semaphore = pipeline.get_user_semaphore(user_id)

        # Verify semaphore created
        assert semaphore is not None, "Semaphore should be created"

        # Verify it's stored in pipeline
        assert user_id in pipeline.user_semaphores, "User should be tracked"

        # Verify same semaphore returned for same user
        semaphore2 = pipeline.get_user_semaphore(user_id)
        assert semaphore is semaphore2, "Should return same semaphore for same user"

        # Verify semaphore limit is 10 (default MAX_REQUESTS_PER_USER)
        assert semaphore._value == 10, "Semaphore should have limit of 10"

    async def test_different_users_get_different_semaphores(self):
        """
        Test that different users get independent semaphores.
        """
        from pipeline_manager import PipelineManager

        pipeline = PipelineManager()
        await pipeline.initialize()

        # Get semaphores for two users
        user1_id = "user_1"
        user2_id = "user_2"

        sem1 = pipeline.get_user_semaphore(user1_id)
        sem2 = pipeline.get_user_semaphore(user2_id)

        # Verify different semaphores
        assert sem1 is not sem2, "Different users should have different semaphores"

        # Verify both tracked
        assert user1_id in pipeline.user_semaphores
        assert user2_id in pipeline.user_semaphores

    async def test_semaphore_acquisition_and_release(self):
        """
        Test basic semaphore acquire and release.
        """
        from pipeline_manager import PipelineManager

        pipeline = PipelineManager()
        await pipeline.initialize()

        user_id = "test_user_acquire"
        semaphore = pipeline.get_user_semaphore(user_id)

        # Check initial value
        initial_value = semaphore._value
        assert initial_value == 10, "Should start at 10"

        # Acquire semaphore
        async with semaphore:
            # Value should decrease
            assert semaphore._value == initial_value - 1, "Should decrease when acquired"

        # After release, should return to original
        assert semaphore._value == initial_value, "Should return to original after release"

    async def test_semaphore_blocks_at_limit(self):
        """
        Test that semaphore blocks when limit reached.

        This is a simple test using asyncio primitives.
        """
        from pipeline_manager import PipelineManager

        pipeline = PipelineManager()
        await pipeline.initialize()

        user_id = "test_user_block"
        semaphore = pipeline.get_user_semaphore(user_id)

        acquired_locks = []
        blocked = asyncio.Event()
        unblocked = asyncio.Event()

        async def acquire_and_hold():
            """Acquire semaphore and hold it"""
            async with semaphore:
                acquired_locks.append(1)
                await asyncio.sleep(0.1)

        async def try_acquire_11th():
            """Try to acquire 11th lock (should block)"""
            # Wait a bit to ensure other 10 are acquired
            await asyncio.sleep(0.05)
            blocked.set()
            async with semaphore:
                unblocked.set()

        # Start 10 tasks that acquire and hold
        tasks = [asyncio.create_task(acquire_and_hold()) for _ in range(10)]

        # Start 11th task that should block
        blocking_task = asyncio.create_task(try_acquire_11th())

        # Wait for 11th task to reach blocking point
        await asyncio.wait_for(blocked.wait(), timeout=1.0)

        # 11th task should still be blocked
        assert not unblocked.is_set(), "11th task should be blocked"

        # Wait for first 10 to complete
        await asyncio.gather(*tasks)

        # Now 11th should unblock
        await asyncio.wait_for(unblocked.wait(), timeout=1.0)
        assert unblocked.is_set(), "11th task should now be unblocked"

        await blocking_task

    async def test_semaphore_cleanup_exists(self):
        """
        Test that semaphore cleanup method exists and can be called.
        """
        from pipeline_manager import PipelineManager

        pipeline = PipelineManager()
        await pipeline.initialize()

        # Create some semaphores
        for i in range(5):
            pipeline.get_user_semaphore(f"user_{i}")

        # Verify cleanup method exists
        assert hasattr(pipeline, 'cleanup_user_semaphores'), \
            "Should have cleanup method"

        # Call cleanup (should not error)
        pipeline.cleanup_user_semaphores()

        # Method executed successfully (no assertion needed if no error)

    async def test_max_requests_per_user_configurable(self):
        """
        Test that MAX_REQUESTS_PER_USER is configurable.

        Note: If pipeline doesn't expose MAX_REQUESTS_PER_USER,
        it may be configured internally. Test skips gracefully.
        """
        from pipeline_manager import PipelineManager

        pipeline = PipelineManager()
        await pipeline.initialize()

        # Check if MAX_REQUESTS_PER_USER exists
        if not hasattr(pipeline, 'MAX_REQUESTS_PER_USER'):
            pytest.skip("MAX_REQUESTS_PER_USER not exposed as public attribute")

        # If it exists, verify default value
        assert pipeline.MAX_REQUESTS_PER_USER == 10, \
            "Default should be 10"


class TestConcurrentRequestBasics:
    """Basic tests for concurrent request handling"""

    async def test_multiple_semaphores_work_independently(self):
        """
        Test that multiple user semaphores work independently.
        """
        from pipeline_manager import PipelineManager

        pipeline = PipelineManager()
        await pipeline.initialize()

        user1_acquired = []
        user2_acquired = []

        async def acquire_for_user1():
            sem = pipeline.get_user_semaphore("user_1")
            async with sem:
                user1_acquired.append(1)
                await asyncio.sleep(0.1)

        async def acquire_for_user2():
            sem = pipeline.get_user_semaphore("user_2")
            async with sem:
                user2_acquired.append(1)
                await asyncio.sleep(0.1)

        # Run 5 concurrent tasks for each user
        tasks = []
        for _ in range(5):
            tasks.append(asyncio.create_task(acquire_for_user1()))
            tasks.append(asyncio.create_task(acquire_for_user2()))

        await asyncio.gather(*tasks)

        # Both users should have processed all their requests
        assert len(user1_acquired) == 5, "User 1 should process all 5"
        assert len(user2_acquired) == 5, "User 2 should process all 5"
