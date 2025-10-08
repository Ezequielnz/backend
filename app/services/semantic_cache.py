"""
Semantic and Exact Cache Service for LLM Operations.
Handles caching of LLM responses with exact hash matching and semantic similarity search.
"""
import logging
import hashlib
import json
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta, timezone
import redis
import asyncpg
from pgvector.asyncpg import register_vector

from app.core.config import settings
from app.services.ml.embedding_pipeline import EmbeddingPipeline, EmbeddingModelType, EmbeddingConfig

logger = logging.getLogger(__name__)


class SemanticCache:
    """
    Service for caching LLM responses using exact hash matching and semantic similarity.
    Supports versioning and embedding model compatibility checks.
    """

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.db_pool: Optional[asyncpg.Pool] = None
        self.embedding_pipeline: Optional[EmbeddingPipeline] = None
        self.exact_cache_ttl = int(settings.LLM_CACHE_TTL or "3600")  # Default 1 hour

        # Initialize connections
        self._init_redis()
        self._init_embedding_pipeline()

    def _init_redis(self):
        """Initialize Redis connection for exact cache."""
        try:
            self.redis_client = redis.from_url(
                settings.CELERY_BROKER_URL,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            self.redis_client.ping()
            logger.info("SemanticCache: Redis connected for exact cache")
        except Exception as e:
            logger.error(f"SemanticCache: Failed to initialize Redis: {e}")
            self.redis_client = None

    def _init_embedding_pipeline(self):
        """Initialize embedding pipeline for semantic cache."""
        try:
            # Use same config as main embedding pipeline
            config = EmbeddingConfig(
                model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
                model_name=settings.EMBEDDING_MODEL_NAME or "sentence-transformers/all-MiniLM-L6-v2",
                batch_size=1,  # Single prompt processing
            )
            self.embedding_pipeline = EmbeddingPipeline(config)
            logger.info("SemanticCache: Embedding pipeline initialized")
        except Exception as e:
            logger.error(f"SemanticCache: Failed to initialize embedding pipeline: {e}")
            self.embedding_pipeline = None

    async def _init_db_pool(self):
        """Initialize database connection pool."""
        if self.db_pool is None:
            try:
                self.db_pool = await asyncpg.create_pool(
                    dsn=settings.DATABASE_URL,
                    min_size=1,
                    max_size=10,
                    command_timeout=60,
                )
                # Register pgvector
                await register_vector(self.db_pool)
                logger.info("SemanticCache: Database pool initialized with pgvector")
            except Exception as e:
                logger.error(f"SemanticCache: Failed to initialize database pool: {e}")
                raise

    async def get_exact(self, prompt_hash: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """
        Get exact cache match by prompt hash.

        Args:
            prompt_hash: SHA256 hash of the prompt
            tenant_id: Tenant identifier

        Returns:
            Cached response data or None if not found
        """
        if not self.redis_client:
            logger.warning("Redis not available for exact cache")
            return None

        try:
            cache_key = f"llm_exact:{tenant_id}:{prompt_hash}"
            cached_data = self.redis_client.get(cache_key)

            if cached_data:
                response_data = json.loads(cached_data)  # type: ignore
                logger.info(f"Exact cache hit for tenant {tenant_id}, hash {prompt_hash[:8]}...")
                return response_data
            else:
                logger.debug(f"Exact cache miss for tenant {tenant_id}, hash {prompt_hash[:8]}...")
                return None

        except Exception as e:
            logger.error(f"Error retrieving exact cache: {e}")
            return None

    async def get_semantic_by_embedding(
        self,
        embedding: List[float],
        tenant_id: str,
        threshold: float = 0.92,
        embedding_model_name: Optional[str] = None,
        embedding_dim: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get semantic cache match by embedding similarity.

        Args:
            embedding: Query embedding vector
            tenant_id: Tenant identifier
            threshold: Similarity threshold (0-1)
            embedding_model_name: Required model name for compatibility
            embedding_dim: Required embedding dimension for compatibility

        Returns:
            Best matching cached response or None
        """
        if not self.db_pool:
            await self._init_db_pool()

        if not embedding_model_name or not embedding_dim:
            logger.error("embedding_model_name and embedding_dim required for semantic search")
            return None

        try:
            async with self.db_pool.acquire() as conn:
                # Find best semantic match with model compatibility
                result = await conn.fetchrow("""
                    SELECT
                        id, prompt_hash, response, model_used, confidence_score,
                        prompt_template_id, prompt_version,
                        1 - (prompt_embedding <=> $1::vector) as similarity
                    FROM llm_cache
                    WHERE tenant_id = $2
                      AND embedding_model_name = $3
                      AND embedding_dim = $4
                      AND created_at > NOW() - INTERVAL '24 hours'  -- Recent entries only
                    ORDER BY prompt_embedding <=> $1::vector
                    LIMIT 1
                """, embedding, tenant_id, embedding_model_name, embedding_dim)

                if result and result['similarity'] >= threshold:
                    logger.info(
                        f"Semantic cache hit for tenant {tenant_id}: "
                        f"similarity={result['similarity']:.3f}, threshold={threshold}"
                    )
                    return dict(result)
                else:
                    similarity = result['similarity'] if result else 0.0
                    logger.debug(
                        f"Semantic cache miss for tenant {tenant_id}: "
                        f"best_similarity={similarity:.3f}, threshold={threshold}"
                    )
                    return None

        except Exception as e:
            logger.error(f"Error in semantic cache search: {e}")
            return None

    async def insert_cache_entry(
        self,
        tenant_id: str,
        prompt_hash: str,
        prompt_text: str,
        prompt_embedding: List[float],
        response: str,
        model_used: str,
        confidence_score: Optional[float] = None,
        prompt_template_id: Optional[str] = None,
        prompt_version: Optional[str] = None,
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """
        Insert new entry into both exact and semantic caches.

        Args:
            tenant_id: Tenant identifier
            prompt_hash: SHA256 hash of prompt
            prompt_text: Full prompt text (for semantic embedding)
            prompt_embedding: Pre-computed embedding vector
            response: LLM response text
            model_used: Model that generated the response
            confidence_score: Optional confidence score
            prompt_template_id: Template identifier
            prompt_version: Template version
            ttl_seconds: Cache TTL in seconds

        Returns:
            True if successfully cached
        """
        if not self.redis_client:
            logger.warning("Redis not available, skipping exact cache")
            return False

        if not self.db_pool:
            await self._init_db_pool()

        try:
            # Get embedding model info
            embedding_model_name = settings.EMBEDDING_MODEL_NAME or "sentence-transformers/all-MiniLM-L6-v2"
            embedding_dim = len(prompt_embedding)

            # Prepare cache data
            cache_data = {
                "response": response,
                "model_used": model_used,
                "confidence_score": confidence_score,
                "prompt_template_id": prompt_template_id,
                "prompt_version": prompt_version,
                "embedding_model_name": embedding_model_name,
                "embedding_dim": embedding_dim,
                "cached_at": datetime.now(timezone.utc).isoformat()
            }

            # Insert exact cache (Redis)
            cache_key = f"llm_exact:{tenant_id}:{prompt_hash}"
            ttl = ttl_seconds or self.exact_cache_ttl
            self.redis_client.setex(cache_key, ttl, json.dumps(cache_data))

            # Insert semantic cache (Postgres)
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO llm_cache (
                        tenant_id, prompt_hash, prompt_embedding,
                        embedding_model_name, embedding_dim,
                        response, model_used, confidence_score,
                        prompt_template_id, prompt_version,
                        ttl_seconds, created_at
                    ) VALUES ($1, $2, $3::vector, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
                """,
                tenant_id, prompt_hash, prompt_embedding,
                embedding_model_name, embedding_dim,
                response, model_used, confidence_score,
                prompt_template_id, prompt_version, ttl
                )

            logger.info(f"Cached LLM response for tenant {tenant_id}, hash {prompt_hash[:8]}...")
            return True

        except Exception as e:
            logger.error(f"Error inserting cache entry: {e}")
            return False

    async def generate_prompt_embedding(self, prompt: str) -> Optional[List[float]]:
        """
        Generate embedding for a prompt using the configured embedding pipeline.

        Args:
            prompt: Prompt text to embed

        Returns:
            Embedding vector or None if failed
        """
        if not self.embedding_pipeline:
            logger.error("Embedding pipeline not available")
            return None

        try:
            # Use synchronous embedding generation (pipeline handles async internally)
            embedding = self.embedding_pipeline.generate_embedding(prompt)
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate prompt embedding: {e}")
            return None

    async def get_cache_stats(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get cache statistics for a tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dictionary with cache statistics
        """
        stats: Dict[str, Any] = {
            "exact_cache_available": self.redis_client is not None,
            "semantic_cache_available": self.db_pool is not None,
            "embedding_pipeline_available": self.embedding_pipeline is not None,
            "exact_cache_entries": 0,
            "semantic_cache_entries_24h": 0
        }

        if self.redis_client:
            try:
                # Count exact cache keys for tenant
                pattern = f"llm_exact:{tenant_id}:*"
                exact_keys = len(self.redis_client.keys(pattern))  # type: ignore
                stats["exact_cache_entries"] = exact_keys
            except Exception as e:
                logger.error(f"Error getting exact cache stats: {e}")
                stats["exact_cache_entries"] = 0

        if self.db_pool:
            try:
                async with self.db_pool.acquire() as conn:
                    semantic_count = await conn.fetchval("""
                        SELECT COUNT(*) FROM llm_cache
                        WHERE tenant_id = $1
                        AND created_at > NOW() - INTERVAL '24 hours'
                    """, tenant_id)
                    stats["semantic_cache_entries_24h"] = semantic_count
            except Exception as e:
                logger.error(f"Error getting semantic cache stats: {e}")
                stats["semantic_cache_entries_24h"] = 0

        return stats

    async def cleanup_expired_cache(self, tenant_id: Optional[str] = None) -> int:
        """
        Clean up expired cache entries.

        Args:
            tenant_id: Specific tenant or None for all

        Returns:
            Number of entries cleaned up
        """
        cleaned = 0

        # Clean Redis exact cache (TTL handles this automatically)
        # But we can clean old semantic cache entries
        if self.db_pool:
            try:
                async with self.db_pool.acquire() as conn:
                    if tenant_id:
                        result = await conn.execute("""
                            DELETE FROM llm_cache
                            WHERE tenant_id = $1
                              AND created_at < NOW() - INTERVAL '24 hours'
                        """, tenant_id)
                    else:
                        result = await conn.execute("""
                            DELETE FROM llm_cache
                            WHERE created_at < NOW() - INTERVAL '24 hours'
                        """)
                    cleaned = int(result.split()[-1])  # "DELETE X" format
                    logger.info(f"Cleaned up {cleaned} expired semantic cache entries")
            except Exception as e:
                logger.error(f"Error cleaning semantic cache: {e}")

        return cleaned


# Global instance
semantic_cache = SemanticCache()