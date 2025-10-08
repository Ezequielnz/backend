"""
Tests for semantic and exact cache functionality.
Ensures cache compatibility, hit rates, and proper storage/retrieval.
"""
import pytest
import asyncio
import json
from unittest.mock import patch, MagicMock, AsyncMock
import redis
import asyncpg
from app.services.semantic_cache import SemanticCache


class TestSemanticCache:
    """Test semantic and exact cache operations."""

    @pytest.fixture
    def redis_mock(self):
        """Mock Redis client."""
        mock_redis = MagicMock(spec=redis.Redis)
        mock_redis.ping.return_value = True
        mock_redis.get.return_value = None
        mock_redis.setex.return_value = True
        mock_redis.keys.return_value = []
        return mock_redis

    @pytest.fixture
    def db_pool_mock(self):
        """Mock database pool."""
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None
        mock_conn.execute.return_value = "INSERT 1"
        mock_conn.fetchval.return_value = 42
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_cm)
        return mock_pool

    @pytest.fixture
    def embedding_pipeline_mock(self):
        """Mock embedding pipeline."""
        mock_pipeline = MagicMock()
        mock_pipeline.generate_embedding.return_value = [0.1, 0.2, 0.3] * 128  # 384 dim
        return mock_pipeline

    @pytest.fixture
    def cache_service(self, redis_mock, db_pool_mock, embedding_pipeline_mock):
        """Cache service with mocked dependencies."""
        with patch('redis.from_url', return_value=redis_mock), \
             patch('app.services.semantic_cache.EmbeddingPipeline', return_value=embedding_pipeline_mock):

            cache = SemanticCache()
            cache.db_pool = db_pool_mock
            cache.embedding_pipeline = embedding_pipeline_mock
            return cache

    @pytest.mark.asyncio
    async def test_exact_cache_miss(self, cache_service, redis_mock):
        """Test exact cache miss."""
        redis_mock.get.return_value = None

        result = await cache_service.get_exact("test_hash", "tenant_123")

        assert result is None
        redis_mock.get.assert_called_once_with("llm_exact:tenant_123:test_hash")

    @pytest.mark.asyncio
    async def test_exact_cache_hit(self, cache_service, redis_mock):
        """Test exact cache hit."""
        cache_data = {
            "response": "Test response",
            "model_used": "gpt-4",
            "confidence_score": 0.9
        }
        redis_mock.get.return_value = json.dumps(cache_data)

        result = await cache_service.get_exact("test_hash", "tenant_123")

        assert result == cache_data
        redis_mock.get.assert_called_once_with("llm_exact:tenant_123:test_hash")

    @pytest.mark.asyncio
    async def test_semantic_cache_miss_low_similarity(self, cache_service, db_pool_mock):
        """Test semantic cache miss due to low similarity."""
        mock_conn = db_pool_mock.acquire.return_value.__aenter__.return_value
        # Return result with low similarity
        mock_conn.fetchrow.return_value = {"similarity": 0.85, "response": "cached response"}

        embedding = [0.1] * 384
        result = await cache_service.get_semantic_by_embedding(
            embedding, "tenant_123", threshold=0.92,
            embedding_model_name="test-model", embedding_dim=384
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_semantic_cache_hit(self, cache_service, db_pool_mock):
        """Test semantic cache hit with high similarity."""
        mock_conn = db_pool_mock.acquire.return_value.__aenter__.return_value
        cache_result = {
            "id": "test-id",
            "prompt_hash": "test-hash",
            "response": "High similarity cached response",
            "model_used": "gpt-4",
            "confidence_score": 0.95,
            "similarity": 0.95
        }
        mock_conn.fetchrow.return_value = cache_result

        embedding = [0.1] * 384
        result = await cache_service.get_semantic_by_embedding(
            embedding, "tenant_123", threshold=0.92,
            embedding_model_name="test-model", embedding_dim=384
        )

        assert result == cache_result

    @pytest.mark.asyncio
    async def test_semantic_cache_model_compatibility(self, cache_service, db_pool_mock):
        """Test that semantic cache enforces model compatibility."""
        mock_conn = db_pool_mock.acquire.return_value.__aenter__.return_value
        # No result returned (different model)
        mock_conn.fetchrow.return_value = None

        embedding = [0.1] * 384
        result = await cache_service.get_semantic_by_embedding(
            embedding, "tenant_123", threshold=0.92,
            embedding_model_name="different-model", embedding_dim=384
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_insert_cache_entry(self, cache_service, redis_mock, db_pool_mock):
        """Test inserting cache entry."""
        mock_conn = db_pool_mock.acquire.return_value.__aenter__.return_value

        embedding = [0.1] * 384
        success = await cache_service.insert_cache_entry(
            tenant_id="tenant_123",
            prompt_hash="test_hash",
            prompt_text="Test prompt",
            prompt_embedding=embedding,
            response="Test response",
            model_used="gpt-4",
            confidence_score=0.9,
            prompt_template_id="template_1",
            prompt_version="v1.0"
        )

        assert success is True
        # Verify Redis exact cache set
        redis_mock.setex.assert_called_once()
        # Verify Postgres semantic cache insert
        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_prompt_embedding(self, cache_service, embedding_pipeline_mock):
        """Test prompt embedding generation."""
        embedding = await cache_service.generate_prompt_embedding("Test prompt")

        assert embedding == [0.1, 0.2, 0.3] * 128  # 384 dim
        embedding_pipeline_mock.generate_embedding.assert_called_once_with("Test prompt")

    @pytest.mark.asyncio
    async def test_cache_stats(self, cache_service, redis_mock, db_pool_mock):
        """Test cache statistics retrieval."""
        mock_conn = db_pool_mock.acquire.return_value.__aenter__.return_value
        redis_mock.keys.return_value = ["key1", "key2", "key3"]
        mock_conn.fetchval.return_value = 42

        stats = await cache_service.get_cache_stats("tenant_123")

        expected_stats = {
            "exact_cache_available": True,
            "semantic_cache_available": True,
            "embedding_pipeline_available": True,
            "exact_cache_entries": 3,
            "semantic_cache_entries_24h": 42
        }
        assert stats == expected_stats

    @pytest.mark.asyncio
    async def test_cleanup_expired_cache(self, cache_service, db_pool_mock):
        """Test cleanup of expired cache entries."""
        mock_conn = db_pool_mock.acquire.return_value.__aenter__.return_value
        mock_conn.execute.return_value = "DELETE 5"

        cleaned = await cache_service.cleanup_expired_cache("tenant_123")

        assert cleaned == 5
        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_semantic_search_requires_model_info(self, cache_service):
        """Test that semantic search requires model name and dimension."""
        embedding = [0.1] * 384

        # Missing model name
        result = await cache_service.get_semantic_by_embedding(
            embedding, "tenant_123", threshold=0.92,
            embedding_model_name=None, embedding_dim=384
        )
        assert result is None

        # Missing dimension
        result = await cache_service.get_semantic_by_embedding(
            embedding, "tenant_123", threshold=0.92,
            embedding_model_name="test-model", embedding_dim=None
        )
        assert result is None

    @pytest.mark.parametrize("threshold,similarity,should_hit", [
        (0.9, 0.95, True),
        (0.9, 0.85, False),
        (0.8, 0.82, True),
        (0.8, 0.75, False),
    ])
    @pytest.mark.asyncio
    async def test_semantic_threshold_logic(self, cache_service, db_pool_mock, threshold, similarity, should_hit):
        """Test semantic cache threshold logic."""
        mock_conn = db_pool_mock.acquire.return_value.__aenter__.return_value

        if should_hit:
            cache_result = {
                "id": "test-id",
                "prompt_hash": "test-hash",
                "response": f"Response with similarity {similarity}",
                "model_used": "gpt-4",
                "confidence_score": 0.9,
                "similarity": similarity
            }
            mock_conn.fetchrow.return_value = cache_result
        else:
            mock_conn.fetchrow.return_value = {"similarity": similarity}

        embedding = [0.1] * 384
        result = await cache_service.get_semantic_by_embedding(
            embedding, "tenant_123", threshold=threshold,
            embedding_model_name="test-model", embedding_dim=384
        )

        if should_hit:
            assert result is not None
            assert result["similarity"] >= threshold
        else:
            assert result is None


if __name__ == "__main__":
    pytest.main([__file__])