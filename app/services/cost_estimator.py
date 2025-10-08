"""
Cost estimation and budget management service for LLM operations.
Handles token counting, cost calculation, and atomic budget reservations using Redis.
"""
import os
import logging
from typing import Optional, Dict, Any
import redis
from app.core.config import settings

logger = logging.getLogger(__name__)

class CostEstimator:
    """
    Service for estimating LLM costs and managing tenant budgets atomically.
    """

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.lua_script_sha: Optional[str] = None
        self._init_redis()

        # Default pricing per model (per 1K tokens)
        # These can be overridden by database table llm_model_pricing
        self.default_pricing = {
            "gpt-4": {"input": 0.03, "output": 0.06},
            "gpt-4-turbo": {"input": 0.01, "output": 0.03},
            "gpt-3.5-turbo": {"input": 0.0015, "output": 0.002},
            "text-embedding-3-small": {"input": 0.00002, "output": 0.0},
            "text-embedding-3-large": {"input": 0.00013, "output": 0.0},
        }

    def _init_redis(self):
        """Initialize Redis connection and load Lua script."""
        try:
            self.redis_client = redis.from_url(
                settings.CELERY_BROKER_URL,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # Test connection
            self.redis_client.ping()

            # Load the atomic budget reservation script
            script_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "scripts", "redis", "atomic_budget_reserve.lua"
            )
            with open(script_path, 'r') as f:
                script_content = f.read()

            self.lua_script_sha = str(self.redis_client.script_load(script_content))
            logger.info("CostEstimator: Redis connected and Lua script loaded")
        except Exception as e:
            logger.error(f"CostEstimator: Failed to initialize Redis: {e}")
            self.redis_client = None

    def _count_tokens(self, text: str, model: str = "gpt-4") -> int:
        """
        Count tokens in text using tiktoken, with fallback heuristic.

        Args:
            text: Text to count tokens for
            model: Model name for tokenization

        Returns:
            Number of tokens
        """
        try:
            import tiktoken

            # Get encoding for the model
            if "gpt-4" in model:
                encoding = tiktoken.encoding_for_model("gpt-4")
            elif "gpt-3.5" in model:
                encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
            else:
                # Fallback to cl100k_base (used by GPT-3.5/4)
                encoding = tiktoken.get_encoding("cl100k_base")

            return len(encoding.encode(text))

        except ImportError:
            logger.warning("tiktoken not available, using character-based heuristic")
            # Fallback: rough estimate of 4 characters per token
            return len(text) // 4
        except Exception as e:
            logger.warning(f"Token counting failed: {e}, using character-based heuristic")
            return len(text) // 4

    def get_model_pricing(self, model_name: str) -> Dict[str, float]:
        """
        Get pricing for a model, checking database first then falling back to defaults.

        Args:
            model_name: Name of the LLM model

        Returns:
            Dict with 'input' and 'output' pricing per 1K tokens
        """
        # TODO: Implement database lookup from llm_model_pricing table
        # For now, use hardcoded defaults
        return self.default_pricing.get(model_name, {"input": 0.002, "output": 0.002})

    def estimate_cost(
        self,
        prompt: str,
        expected_output_tokens: int = 100,
        model: str = "gpt-4"
    ) -> float:
        """
        Estimate total cost for an LLM call.

        Args:
            prompt: Input prompt text
            expected_output_tokens: Expected number of output tokens
            model: Model name

        Returns:
            Estimated cost in USD
        """
        input_tokens = self._count_tokens(prompt, model)
        pricing = self.get_model_pricing(model)

        input_cost = (input_tokens / 1000) * pricing["input"]
        output_cost = (expected_output_tokens / 1000) * pricing["output"]

        total_cost = input_cost + output_cost
        logger.debug(
            f"Cost estimate for {model}: {input_tokens} input tokens (${input_cost:.6f}) + "
            f"{expected_output_tokens} output tokens (${output_cost:.6f}) = ${total_cost:.6f}"
        )

        return total_cost

    def reserve_budget(self, tenant_id: str, amount: float) -> bool:
        """
        Atomically reserve budget for a tenant.

        Args:
            tenant_id: Tenant identifier
            amount: Amount to reserve

        Returns:
            True if reservation successful, False if budget exceeded
        """
        if not self.redis_client or not self.lua_script_sha:
            logger.error("Redis not available for budget reservation")
            return False

        try:
            # Keys for the Lua script
            budget_key = f"llm_budget:{tenant_id}"
            limit_key = f"llm_budget_limit:{tenant_id}"

            # Ensure budget limit exists (set default if not)
            budget_limit = float(os.getenv("LLM_DAILY_BUDGET", "50.00"))
            self.redis_client.set(limit_key, budget_limit, nx=True)  # Set only if not exists

            # Execute atomic reservation
            result = self.redis_client.evalsha(
                self.lua_script_sha,
                2,  # Number of keys
                budget_key,
                limit_key,
                str(amount)
            )

            success = result == 1
            if success:
                logger.info(f"Budget reserved: {tenant_id} += ${amount:.6f}")
            else:
                logger.warning(f"Budget reservation failed: {tenant_id} would exceed limit with ${amount:.6f}")

            return success

        except Exception as e:
            logger.error(f"Budget reservation error: {e}")
            return False

    def release_budget(self, tenant_id: str, amount: float) -> bool:
        """
        Release previously reserved budget (for rollback on failure).

        Args:
            tenant_id: Tenant identifier
            amount: Amount to release

        Returns:
            True if successful
        """
        if not self.redis_client:
            logger.error("Redis not available for budget release")
            return False

        try:
            budget_key = f"llm_budget:{tenant_id}"
            # Use INCRBYFLOAT with negative value to decrease the reserved amount
            self.redis_client.incrbyfloat(budget_key, -amount)
            logger.info(f"Budget released: {tenant_id} -= ${amount:.6f}")
            return True

        except Exception as e:
            logger.error(f"Budget release error: {e}")
            return False

    def get_budget_status(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get current budget status for a tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dict with current_reserved, budget_limit, and available_budget
        """
        if not self.redis_client:
            return {"error": "Redis not available"}

        try:
            budget_key = f"llm_budget:{tenant_id}"
            limit_key = f"llm_budget_limit:{tenant_id}"

            current_reserved_val = self.redis_client.get(budget_key)  # type: ignore
            current_reserved = float(current_reserved_val) if current_reserved_val else 0.0  # type: ignore

            budget_limit_val = self.redis_client.get(limit_key)  # type: ignore
            budget_limit = float(budget_limit_val) if budget_limit_val else 0.0  # type: ignore

            return {
                "current_reserved": current_reserved,
                "budget_limit": budget_limit,
                "available_budget": budget_limit - current_reserved
            }

        except Exception as e:
            logger.error(f"Budget status error: {e}")
            return {"error": str(e)}

# Global instance
cost_estimator = CostEstimator()