"""
Tests for atomic budget reservation functionality.
Tests concurrent reservations to ensure budget limits are never exceeded.
"""
import pytest
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, MagicMock
import redis
from app.services.cost_estimator import CostEstimator


class TestAtomicBudgetReservation:
    """Test atomic budget reservation with concurrency."""

    @pytest.fixture
    def redis_mock(self):
        """Mock Redis client for testing."""
        mock_redis = MagicMock(spec=redis.Redis)
        mock_redis.ping.return_value = True
        mock_redis.script_load.return_value = "test_sha"
        mock_redis.evalsha.return_value = 1  # Default to success
        mock_redis.set.return_value = True
        mock_redis.get.return_value = "0"  # Default to 0
        return mock_redis

    @pytest.fixture
    def cost_estimator(self, redis_mock):
        """Cost estimator with mocked Redis."""
        with patch('redis.from_url', return_value=redis_mock):
            estimator = CostEstimator()
            # Manually set the mock client
            estimator.redis_client = redis_mock
            estimator.lua_script_sha = "test_sha"
            return estimator

    def test_single_reservation_success(self, cost_estimator, redis_mock):
        """Test successful single budget reservation."""
        redis_mock.evalsha.return_value = 1  # Success

        result = cost_estimator.reserve_budget("tenant_123", 10.0)

        assert result is True
        redis_mock.evalsha.assert_called_once_with(
            "test_sha", 2, "llm_budget:tenant_123", "llm_budget_limit:tenant_123", "10.0"
        )

    def test_single_reservation_failure(self, cost_estimator, redis_mock):
        """Test failed budget reservation when limit exceeded."""
        redis_mock.evalsha.return_value = 0  # Failure

        result = cost_estimator.reserve_budget("tenant_123", 100.0)

        assert result is False

    def test_budget_release(self, cost_estimator, redis_mock):
        """Test budget release functionality."""
        result = cost_estimator.release_budget("tenant_123", 5.0)

        assert result is True
        redis_mock.incrbyfloat.assert_called_once_with("llm_budget:tenant_123", -5.0)

    def test_concurrent_reservations_under_limit(self, cost_estimator, redis_mock):
        """Test concurrent reservations that stay under budget limit."""
        budget_limit = 50.0
        num_threads = 10
        amount_per_thread = 4.0  # 10 * 4.0 = 40.0 < 50.0

        # Mock successful reservations
        redis_mock.evalsha.return_value = 1
        redis_mock.get.side_effect = lambda key: "50.0" if "limit" in key else "0"

        results = []
        threads = []

        def reserve_budget_thread(thread_id):
            """Worker function for each thread."""
            result = cost_estimator.reserve_budget("tenant_concurrent", amount_per_thread)
            results.append(result)
            return result

        # Start concurrent reservations
        for i in range(num_threads):
            thread = threading.Thread(target=reserve_budget_thread, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All reservations should succeed
        assert all(results)
        assert len(results) == num_threads

        # Verify evalsha was called the expected number of times
        assert redis_mock.evalsha.call_count == num_threads

    def test_concurrent_reservations_over_limit(self, cost_estimator, redis_mock):
        """Test concurrent reservations that exceed budget limit."""
        budget_limit = 20.0
        num_threads = 10
        amount_per_thread = 3.0  # 10 * 3.0 = 30.0 > 20.0

        # Track reservation attempts
        call_count = 0
        def mock_evalsha(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Allow first few reservations, then fail
            if call_count <= 6:  # 6 * 3.0 = 18.0, still under 20.0
                return 1
            else:
                return 0

        redis_mock.evalsha.side_effect = mock_evalsha
        redis_mock.get.side_effect = lambda key: "20.0" if "limit" in key else "0"

        results = []
        threads = []

        def reserve_budget_thread(thread_id):
            """Worker function for each thread."""
            result = cost_estimator.reserve_budget("tenant_over_limit", amount_per_thread)
            results.append(result)
            return result

        # Start concurrent reservations
        for i in range(num_threads):
            thread = threading.Thread(target=reserve_budget_thread, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Count successful vs failed reservations
        successful = sum(1 for r in results if r)
        failed = sum(1 for r in results if not r)

        # Some should succeed, some should fail
        assert successful > 0
        assert failed > 0
        assert successful + failed == num_threads

        # Verify total successful reservations don't exceed budget
        max_possible_successful = int(budget_limit // amount_per_thread)  # 20.0 // 3.0 = 6
        assert successful <= max_possible_successful

    def test_budget_status(self, cost_estimator, redis_mock):
        """Test budget status retrieval."""
        redis_mock.get.side_effect = lambda key: {
            "llm_budget:tenant_123": "15.5",
            "llm_budget_limit:tenant_123": "50.0"
        }.get(key, "0")

        status = cost_estimator.get_budget_status("tenant_123")

        expected = {
            "current_reserved": 15.5,
            "budget_limit": 50.0,
            "available_budget": 34.5
        }
        assert status == expected

    def test_token_counting_with_tiktoken(self, cost_estimator):
        """Test token counting with tiktoken."""
        text = "Hello world, this is a test message for token counting."
        tokens = cost_estimator._count_tokens(text, "gpt-4")

        # Should return a reasonable token count
        assert isinstance(tokens, int)
        assert tokens > 0
        # Rough estimate: text has ~50 characters, should be ~12-15 tokens
        assert 10 <= tokens <= 20

    def test_token_counting_fallback(self, cost_estimator):
        """Test token counting fallback when tiktoken unavailable."""
        with patch.dict('sys.modules', {'tiktoken': None}):
            text = "Hello world, this is a test message."
            tokens = cost_estimator._count_tokens(text, "gpt-4")

            # Fallback: characters // 4
            expected = len(text) // 4
            assert tokens == expected

    def test_cost_estimation(self, cost_estimator):
        """Test cost estimation calculation."""
        prompt = "Test prompt for cost estimation"
        cost = cost_estimator.estimate_cost(prompt, expected_output_tokens=100, model="gpt-4")

        assert isinstance(cost, float)
        assert cost > 0
        # GPT-4 pricing: ~$0.03 per 1K input tokens, ~$0.06 per 1K output tokens
        # Prompt is short, so cost should be small
        assert cost < 0.01  # Less than 1 cent

    @pytest.mark.parametrize("model,expected_range", [
        ("gpt-4", (0.001, 0.1)),
        ("gpt-3.5-turbo", (0.0001, 0.01)),
        ("unknown-model", (0.0001, 0.01)),  # Falls back to default
    ])
    def test_cost_estimation_different_models(self, cost_estimator, model, expected_range):
        """Test cost estimation for different models."""
        prompt = "Test prompt for " + model
        cost = cost_estimator.estimate_cost(prompt, expected_output_tokens=50, model=model)

        assert expected_range[0] <= cost <= expected_range[1]


if __name__ == "__main__":
    pytest.main([__file__])