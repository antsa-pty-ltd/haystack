"""
Rate Limiting V2 Tests

Simplified rate limiting tests that focus on measurable behavior and timing verification
instead of complex AsyncGenerator mocking. These tests verify the core functionality of
per-user rate limiting without requiring complex stream mocking.

Key improvements over test_rate_limiting_enforcement.py:
- Use timing-based verification instead of AsyncGenerator mocking
- Focus on measurable behavior (timing, semaphore values, concurrent execution)
- Avoid complex mocking that caused tests to be skipped
- Follow patterns from test_rate_limiting_simple.py
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

import pytest
import asyncio
import time
from typing import List, Dict

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class TestRateLimitingTimingBased:
    """Tests that verify rate limiting through timing and concurrency measurement"""

    async def test_11th_request_waits_timing_verification(self):
        """
        Test that 11th request waits when 10 are active (timing-based verification).

        Flow:
        1. Start 10 tasks that hold semaphore for 0.3 seconds
        2. Start 11th task that should block
        3. Measure timing to verify 11th task had to wait
        4. Verify all tasks eventually complete

        This tests:
        - Rate limiting enforcement (max 10 concurrent)
        - Blocking behavior for requests beyond limit
        - Proper semaphore release after completion
        """
        from pipeline_manager import PipelineManager

        pipeline = PipelineManager()
        await pipeline.initialize()

        user_id = "test_user_11th"
        semaphore = pipeline.get_user_semaphore(user_id)

        completion_times: List[float] = []
        start_time = time.time()

        async def hold_semaphore(task_id: int):
            """Acquire semaphore and hold for 0.3 seconds"""
            async with semaphore:
                # Record when we acquired the semaphore
                acquired_at = time.time() - start_time
                await asyncio.sleep(0.3)  # Hold for 300ms
                completion_times.append((task_id, acquired_at))

        # Start 10 tasks simultaneously
        tasks = [asyncio.create_task(hold_semaphore(i)) for i in range(10)]

        # Small delay to ensure first 10 have acquired
        await asyncio.sleep(0.05)

        # Start 11th task (should block until one of first 10 releases)
        eleventh_start = time.time()
        eleventh_task = asyncio.create_task(hold_semaphore(11))

        # Wait for all tasks to complete
        await asyncio.gather(*tasks, eleventh_task)

        # Calculate when 11th task actually acquired semaphore
        eleventh_acquired = next(t[1] for t in completion_times if t[0] == 11)

        # 11th task should have waited at least ~300ms for a slot to free up
        # (accounting for timing variations, we check for > 250ms)
        assert eleventh_acquired > 0.25, \
            f"11th task acquired too quickly ({eleventh_acquired:.3f}s), should have waited ~300ms"

        # All 11 tasks should have completed
        assert len(completion_times) == 11, "All 11 tasks should complete"

        # Semaphore should be back to full capacity
        assert semaphore._value == 10, "Semaphore should return to 10 after all tasks complete"

    async def test_cleanup_removes_inactive_semaphores(self):
        """
        Test that cleanup removes inactive semaphores (memory leak prevention).

        Flow:
        1. Create semaphores for 5 users
        2. Use semaphores and release them
        3. Call cleanup
        4. Verify inactive semaphores are removed

        This tests:
        - Memory leak prevention
        - Cleanup of unused resources
        - Proper tracking of active users
        """
        from pipeline_manager import PipelineManager

        pipeline = PipelineManager()
        await pipeline.initialize()

        # Create semaphores for multiple users
        user_ids = [f"user_{i}" for i in range(5)]
        for user_id in user_ids:
            semaphore = pipeline.get_user_semaphore(user_id)
            assert semaphore is not None

        # Verify all created
        assert len(pipeline.user_semaphores) == 5, "Should have 5 user semaphores"

        # Use and release semaphores (simulate completed requests)
        for user_id in user_ids:
            semaphore = pipeline.get_user_semaphore(user_id)
            async with semaphore:
                await asyncio.sleep(0.01)

        # All semaphores should now be unlocked
        for user_id in user_ids:
            semaphore = pipeline.user_semaphores[user_id]
            assert not semaphore.locked(), f"Semaphore for {user_id} should be unlocked"

        # Call cleanup (no active requests)
        pipeline.cleanup_user_semaphores()

        # Since no tasks are tracked in active_requests, all should be removed
        assert len(pipeline.user_semaphores) == 0, \
            "Cleanup should remove all inactive semaphores"

    async def test_20_fast_sequential_requests_max_10_concurrent(self):
        """
        Test 20 fast sequential requests verify max 10 concurrent.

        Flow:
        1. Start 20 tasks that each hold semaphore briefly
        2. Monitor concurrent execution throughout
        3. Verify never more than 10 concurrent
        4. Verify all 20 complete successfully

        This tests:
        - Concurrent limit enforcement under load
        - Proper queuing of excess requests
        - No deadlocks with sequential requests
        """
        from pipeline_manager import PipelineManager

        pipeline = PipelineManager()
        await pipeline.initialize()

        user_id = "test_user_20_requests"
        semaphore = pipeline.get_user_semaphore(user_id)

        concurrent_count = 0
        max_concurrent = 0
        concurrent_lock = asyncio.Lock()
        completed_count = 0

        async def monitored_request(task_id: int):
            """Request that tracks concurrent execution"""
            nonlocal concurrent_count, max_concurrent, completed_count

            async with semaphore:
                # Track concurrent execution
                async with concurrent_lock:
                    concurrent_count += 1
                    if concurrent_count > max_concurrent:
                        max_concurrent = concurrent_count

                # Hold briefly
                await asyncio.sleep(0.05)

                # Decrement concurrent count
                async with concurrent_lock:
                    concurrent_count -= 1
                    completed_count += 1

        # Start 20 tasks
        tasks = [asyncio.create_task(monitored_request(i)) for i in range(20)]

        # Wait for all to complete
        await asyncio.gather(*tasks)

        # Verify results
        assert max_concurrent <= 10, \
            f"Max concurrent was {max_concurrent}, should never exceed 10"
        assert completed_count == 20, \
            f"Should complete all 20 tasks, completed {completed_count}"
        assert semaphore._value == 10, \
            "Semaphore should return to 10 after all tasks complete"

    async def test_error_releases_semaphore_no_deadlock(self):
        """
        Test that errors release semaphore (no deadlock).

        Flow:
        1. Start task that acquires semaphore and raises error
        2. Verify error is raised
        3. Verify semaphore is released despite error
        4. Verify subsequent tasks can acquire

        This tests:
        - Proper cleanup on error
        - No semaphore leaks
        - No deadlocks from failed requests
        """
        from pipeline_manager import PipelineManager

        pipeline = PipelineManager()
        await pipeline.initialize()

        user_id = "test_user_error"
        semaphore = pipeline.get_user_semaphore(user_id)

        # Check initial state
        assert semaphore._value == 10, "Should start at 10"

        async def failing_task():
            """Task that raises error while holding semaphore"""
            async with semaphore:
                await asyncio.sleep(0.01)
                raise ValueError("Simulated error")

        # Run failing task
        with pytest.raises(ValueError, match="Simulated error"):
            await failing_task()

        # Semaphore should be released despite error
        assert semaphore._value == 10, \
            "Semaphore should be released after error"

        # Verify subsequent tasks can still acquire
        success = False

        async def subsequent_task():
            nonlocal success
            async with semaphore:
                await asyncio.sleep(0.01)
                success = True

        await subsequent_task()
        assert success, "Subsequent task should successfully acquire semaphore"

    async def test_different_users_independent_limits(self):
        """
        Test that different users have independent rate limits.

        Flow:
        1. User A starts 10 concurrent tasks
        2. User B starts 10 concurrent tasks
        3. Both should process concurrently (20 total)
        4. Verify independent semaphores

        This tests:
        - Per-user isolation
        - Independent concurrent limits
        - No cross-user blocking
        """
        from pipeline_manager import PipelineManager

        pipeline = PipelineManager()
        await pipeline.initialize()

        user_a = "user_a_independent"
        user_b = "user_b_independent"

        user_a_count = 0
        user_b_count = 0
        count_lock = asyncio.Lock()

        async def user_a_task():
            """Task for user A"""
            nonlocal user_a_count
            semaphore = pipeline.get_user_semaphore(user_a)
            async with semaphore:
                async with count_lock:
                    user_a_count += 1
                await asyncio.sleep(0.1)

        async def user_b_task():
            """Task for user B"""
            nonlocal user_b_count
            semaphore = pipeline.get_user_semaphore(user_b)
            async with semaphore:
                async with count_lock:
                    user_b_count += 1
                await asyncio.sleep(0.1)

        # Start 10 tasks for each user simultaneously
        tasks = []
        for _ in range(10):
            tasks.append(asyncio.create_task(user_a_task()))
            tasks.append(asyncio.create_task(user_b_task()))

        # All tasks should complete without cross-user blocking
        start_time = time.time()
        await asyncio.gather(*tasks)
        duration = time.time() - start_time

        # Both users should complete all tasks
        assert user_a_count == 10, f"User A should complete 10 tasks, got {user_a_count}"
        assert user_b_count == 10, f"User B should complete 10 tasks, got {user_b_count}"

        # Duration should be ~100ms (one batch), not ~200ms (if serialized)
        # Allow some overhead, but should be much less than 180ms
        assert duration < 0.18, \
            f"Duration {duration:.3f}s suggests serialization, should be ~0.1s for concurrent"

        # Verify separate semaphores
        sem_a = pipeline.user_semaphores[user_a]
        sem_b = pipeline.user_semaphores[user_b]
        assert sem_a is not sem_b, "Users should have different semaphores"

    async def test_rate_limit_configuration_via_settings(self):
        """
        Test that rate limit is configurable via settings.

        Flow:
        1. Initialize pipeline manager
        2. Verify max_requests_per_user is set from config
        3. Verify semaphores created with correct limit

        This tests:
        - Configuration propagation
        - Proper initialization from settings
        """
        from pipeline_manager import PipelineManager
        from config import settings

        pipeline = PipelineManager()
        await pipeline.initialize()

        # Verify pipeline reads from settings
        assert hasattr(pipeline, 'max_requests_per_user'), \
            "Pipeline should have max_requests_per_user attribute"
        assert pipeline.max_requests_per_user == settings.max_requests_per_user, \
            "Pipeline should use settings value"

        # Verify semaphores created with this limit
        user_id = "test_config_user"
        semaphore = pipeline.get_user_semaphore(user_id)
        assert semaphore._value == settings.max_requests_per_user, \
            f"Semaphore should have limit of {settings.max_requests_per_user}"

    async def test_semaphore_memory_leak_prevention(self):
        """
        Test that semaphores don't leak memory with many users.

        Flow:
        1. Simulate 100 different users making requests
        2. All complete successfully
        3. Call cleanup
        4. Verify semaphores are removed

        This tests:
        - Scalability with many users
        - Memory leak prevention
        - Cleanup effectiveness
        """
        from pipeline_manager import PipelineManager

        pipeline = PipelineManager()
        await pipeline.initialize()

        # Simulate 100 users making requests
        user_count = 100
        completed_users = []

        async def user_request(user_id: str):
            """Single request from a user"""
            semaphore = pipeline.get_user_semaphore(user_id)
            async with semaphore:
                await asyncio.sleep(0.01)
                completed_users.append(user_id)

        # Create tasks for all users
        tasks = [
            asyncio.create_task(user_request(f"user_{i}"))
            for i in range(user_count)
        ]

        # Wait for all to complete
        await asyncio.gather(*tasks)

        # Verify all completed
        assert len(completed_users) == user_count, \
            f"Should complete {user_count} requests, got {len(completed_users)}"

        # Before cleanup, should have semaphores for all users
        assert len(pipeline.user_semaphores) == user_count, \
            f"Should have {user_count} semaphores before cleanup"

        # Call cleanup (no active requests)
        pipeline.cleanup_user_semaphores()

        # After cleanup, all inactive semaphores should be removed
        assert len(pipeline.user_semaphores) == 0, \
            "Cleanup should remove all inactive semaphores"


class TestRateLimitingEdgeCases:
    """Tests for edge cases and corner scenarios"""

    async def test_rapid_acquire_release_cycles(self):
        """
        Test rapid acquire/release cycles don't cause issues.

        Flow:
        1. Single user makes 50 very fast requests
        2. Each holds semaphore for 10ms
        3. Verify all complete successfully
        4. Verify semaphore state is correct

        This tests:
        - High-frequency usage
        - Proper acquire/release mechanics
        - No race conditions
        """
        from pipeline_manager import PipelineManager

        pipeline = PipelineManager()
        await pipeline.initialize()

        user_id = "test_rapid_user"
        semaphore = pipeline.get_user_semaphore(user_id)
        completed = []

        async def rapid_request(request_id: int):
            """Very fast request"""
            async with semaphore:
                await asyncio.sleep(0.01)
                completed.append(request_id)

        # Start 50 rapid requests
        tasks = [asyncio.create_task(rapid_request(i)) for i in range(50)]
        await asyncio.gather(*tasks)

        # All should complete
        assert len(completed) == 50, f"Should complete 50 requests, got {len(completed)}"

        # Semaphore should be back to full capacity
        assert semaphore._value == 10, "Semaphore should be at full capacity"

    async def test_mixed_duration_requests(self):
        """
        Test mixed duration requests (some fast, some slow).

        Flow:
        1. Start 5 slow requests (300ms each)
        2. Start 15 fast requests (10ms each)
        3. Verify all complete
        4. Verify fast requests don't get starved

        This tests:
        - Fair scheduling
        - No starvation of fast requests
        - Proper queue management
        """
        from pipeline_manager import PipelineManager

        pipeline = PipelineManager()
        await pipeline.initialize()

        user_id = "test_mixed_user"
        semaphore = pipeline.get_user_semaphore(user_id)
        slow_completed = []
        fast_completed = []

        async def slow_request(request_id: int):
            """Slow request (300ms)"""
            async with semaphore:
                await asyncio.sleep(0.3)
                slow_completed.append(request_id)

        async def fast_request(request_id: int):
            """Fast request (10ms)"""
            async with semaphore:
                await asyncio.sleep(0.01)
                fast_completed.append(request_id)

        # Start all tasks
        tasks = []
        for i in range(5):
            tasks.append(asyncio.create_task(slow_request(i)))
        for i in range(15):
            tasks.append(asyncio.create_task(fast_request(i)))

        start_time = time.time()
        await asyncio.gather(*tasks)
        duration = time.time() - start_time

        # All should complete
        assert len(slow_completed) == 5, f"Should complete 5 slow requests"
        assert len(fast_completed) == 15, f"Should complete 15 fast requests"

        # Duration should be reasonable (not serialized)
        # With 10 concurrent: first batch processes, then second batch
        # Should take roughly 2 batches * 300ms = ~600ms
        assert duration < 1.0, \
            f"Duration {duration:.3f}s is too long, suggests issues with concurrency"

    async def test_semaphore_state_after_timeout(self):
        """
        Test semaphore state remains correct even with timeouts.

        Flow:
        1. Start task that holds semaphore
        2. Start second task that times out waiting
        3. Verify semaphore is still usable
        4. Verify no corruption

        This tests:
        - Timeout handling
        - Semaphore integrity after timeout
        - No state corruption
        """
        from pipeline_manager import PipelineManager

        pipeline = PipelineManager()
        await pipeline.initialize()

        user_id = "test_timeout_user"
        semaphore = pipeline.get_user_semaphore(user_id)

        # Fill all 10 slots
        async def hold_long():
            async with semaphore:
                await asyncio.sleep(0.5)

        # Start 10 tasks that will hold for 500ms
        holding_tasks = [asyncio.create_task(hold_long()) for _ in range(10)]

        # Try to acquire 11th with short timeout (should fail)
        timeout_occurred = False

        async def try_with_timeout():
            nonlocal timeout_occurred
            try:
                await asyncio.wait_for(
                    semaphore.acquire(),
                    timeout=0.1
                )
                semaphore.release()  # Won't reach here
            except asyncio.TimeoutError:
                timeout_occurred = True

        await try_with_timeout()
        assert timeout_occurred, "Should have timed out"

        # Wait for holding tasks to complete
        await asyncio.gather(*holding_tasks)

        # Semaphore should be back to normal
        assert semaphore._value == 10, \
            "Semaphore should be at full capacity after timeout scenario"

        # Should be able to acquire successfully now
        success = False
        async with semaphore:
            success = True
        assert success, "Should be able to acquire after timeout scenario"

    async def test_concurrent_cleanup_calls(self):
        """
        Test that concurrent cleanup calls don't cause issues.

        Flow:
        1. Create multiple semaphores
        2. Call cleanup multiple times concurrently
        3. Verify no errors occur
        4. Verify cleanup is idempotent

        This tests:
        - Thread safety of cleanup
        - Idempotent cleanup
        - No race conditions in cleanup
        """
        from pipeline_manager import PipelineManager

        pipeline = PipelineManager()
        await pipeline.initialize()

        # Create some semaphores
        for i in range(10):
            pipeline.get_user_semaphore(f"user_{i}")

        # Use and release them
        for i in range(10):
            semaphore = pipeline.get_user_semaphore(f"user_{i}")
            async with semaphore:
                await asyncio.sleep(0.01)

        # Call cleanup multiple times concurrently
        async def cleanup_task():
            pipeline.cleanup_user_semaphores()
            await asyncio.sleep(0.001)
            pipeline.cleanup_user_semaphores()

        # Run multiple cleanup tasks concurrently
        cleanup_tasks = [asyncio.create_task(cleanup_task()) for _ in range(5)]
        await asyncio.gather(*cleanup_tasks)

        # Should not error and all should be cleaned up
        assert len(pipeline.user_semaphores) == 0, \
            "All semaphores should be cleaned up"
