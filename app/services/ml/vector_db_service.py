"""
Vector Database Service for Tenant-Specific Vector Operations
Phase 2: Vector Enrichment
"""

import logging
import json
import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Set
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
import asyncio
from contextlib import asynccontextmanager

from supabase.client import Client
from app.db.supabase_client import get_supabase_service_client

logger = logging.getLogger(__name__)


class VectorSearchType(Enum):
    """Types of vector search operations."""
    SIMILARITY = "similarity"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class VectorIndexType(Enum):
    """Types of vector indexes."""
    IVF_FLAT = "ivfflat"
    HNSW = "hnsw"
    EXACT = "exact"


@dataclass
class VectorSearchResult:
    """Result of a vector search operation."""
    content_id: str
    content_type: str
    similarity_score: float
    metadata: Dict[str, Any]
    vector_id: str


@dataclass
class EmbeddingResult:
    """Result of an embedding operation."""
    vector_id: str
    tenant_id: str
    content_type: str
    content_id: str
    embedding_vector: List[float]
    metadata: Dict[str, Any]
    pii_hash: Optional[str]


class VectorDBService:
    """
    Service for managing tenant-specific vector database operations.
    Provides tenant isolation, PII protection, and efficient vector search.
    """

    def __init__(self):
        self.supabase: Client = get_supabase_service_client()
        self.table_name = "vector_embeddings"
        self.queue_table_name = "embedding_queue"
        self.pii_log_table_name = "pii_protection_log"
        self.search_log_table_name = "vector_search_logs"

    def _ensure_tenant_context(self, tenant_id: str) -> None:
        """Ensure tenant context is set for RLS policies."""
        try:
            # Set tenant context for Row Level Security
            self.supabase.rpc("set_tenant_context", {"tenant_id": tenant_id}).execute()
        except Exception as e:
            logger.warning(f"Failed to set tenant context: {e}")

    def _log_search_operation(
        self,
        tenant_id: str,
        search_query: str,
        search_type: VectorSearchType,
        filters_used: Dict[str, Any],
        results_count: int,
        execution_time_ms: int,
        cache_hit: bool = False
    ) -> None:
        """Log vector search operations for analytics."""
        try:
            search_log = {
                "tenant_id": tenant_id,
                "search_query": search_query,
                "search_type": search_type.value,
                "filters_used": filters_used,
                "results_count": results_count,
                "execution_time_ms": execution_time_ms,
                "cache_hit": cache_hit
            }

            table = self.supabase.table(self.search_log_table_name)
            table.insert(search_log).execute()

        except Exception as e:
            logger.warning(f"Failed to log search operation: {e}")

    async def store_embedding(
        self,
        tenant_id: str,
        content_type: str,
        content_id: str,
        embedding_vector: List[float],
        metadata: Optional[Dict[str, Any]] = None,
        pii_hash: Optional[str] = None,
        priority: str = "medium"
    ) -> str:
        """
        Store a vector embedding with tenant isolation.

        Args:
            tenant_id: Tenant ID for isolation
            content_type: Type of content (e.g., 'product_description')
            content_id: Unique ID of the content
            embedding_vector: Vector embedding as list of floats
            metadata: Additional metadata
            pii_hash: Hash of PII data for compliance
            priority: Priority level for queue processing

        Returns:
            Vector ID of stored embedding
        """
        self._ensure_tenant_context(tenant_id)

        if metadata is None:
            metadata = {}

        # Create content hash for duplicate detection
        content_hash = self._hash_content_for_duplicate_detection(
            content_type, content_id, embedding_vector
        )

        embedding_data = {
            "tenant_id": tenant_id,
            "content_type": content_type,
            "content_id": content_id,
            "content_hash": content_hash,
            "embedding_vector": embedding_vector,
            "metadata": metadata,
            "pii_hash": pii_hash,
            "priority": priority,
            "status": "completed"
        }

        try:
            table = self.supabase.table(self.table_name)
            result = table.insert(embedding_data).execute()

            if result.data:
                vector_id = result.data[0]["id"]
                logger.info(f"Stored embedding for tenant {tenant_id}, content {content_id}")
                return vector_id
            else:
                raise Exception("Failed to store embedding - no data returned")

        except Exception as e:
            logger.error(f"Failed to store embedding: {e}")
            raise

    async def search_similar(
        self,
        tenant_id: str,
        query_vector: List[float],
        content_type: Optional[str] = None,
        limit: int = 10,
        threshold: float = 0.7,
        search_type: VectorSearchType = VectorSearchType.SIMILARITY
    ) -> List[VectorSearchResult]:
        """
        Search for similar vectors with tenant isolation.

        Args:
            tenant_id: Tenant ID for isolation
            query_vector: Query vector for similarity search
            content_type: Filter by content type (optional)
            limit: Maximum number of results
            threshold: Minimum similarity threshold
            search_type: Type of search to perform

        Returns:
            List of similar vectors with metadata
        """
        import time
        start_time = time.time()

        self._ensure_tenant_context(tenant_id)

        try:
            # Build the query
            table = self.supabase.table(self.table_name)

            # Apply tenant filter
            query = table.select("*").eq("tenant_id", tenant_id)

            # Apply content type filter if specified
            if content_type:
                query = query.eq("content_type", content_type)

            # Apply status filter (only completed embeddings)
            query = query.eq("status", "completed")

            # Execute query
            result = query.execute()

            if not result.data:
                return []

            # Perform vector similarity search in Python
            # (In production, you'd want to use pgvector's similarity operators)
            results = []
            for record in result.data:
                stored_vector = record.get("embedding_vector", [])
                if stored_vector:
                    similarity = self._cosine_similarity(query_vector, stored_vector)
                    if similarity >= threshold:
                        results.append({
                            "content_id": record["content_id"],
                            "content_type": record["content_type"],
                            "similarity_score": similarity,
                            "metadata": record.get("metadata", {}),
                            "vector_id": record["id"]
                        })

            # Sort by similarity and limit results
            results.sort(key=lambda x: x["similarity_score"], reverse=True)
            results = results[:limit]

            # Log search operation
            execution_time_ms = int((time.time() - start_time) * 1000)
            self._log_search_operation(
                tenant_id=tenant_id,
                search_query=f"vector_search_{search_type.value}",
                search_type=search_type,
                filters_used={"content_type": content_type, "threshold": threshold},
                results_count=len(results),
                execution_time_ms=execution_time_ms
            )

            return results

        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            raise

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        try:
            v1 = np.array(vec1, dtype=float)
            v2 = np.array(vec2, dtype=float)

            dot_product = np.dot(v1, v2)
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            return float(dot_product / (norm1 * norm2))
        except Exception:
            return 0.0

    def _hash_content_for_duplicate_detection(
        self,
        content_type: str,
        content_id: str,
        vector: List[float]
    ) -> str:
        """Create hash for duplicate detection."""
        import hashlib

        # Create a deterministic string from the vector
        vector_str = json.dumps(vector, sort_keys=True)
        combined = f"{content_type}:{content_id}:{vector_str}"

        return hashlib.sha256(combined.encode()).hexdigest()

    async def queue_embedding(
        self,
        tenant_id: str,
        content_type: str,
        content_id: str,
        priority: str = "medium",
        scheduled_for: Optional[datetime] = None
    ) -> str:
        """
        Queue content for embedding processing.

        Args:
            tenant_id: Tenant ID
            content_type: Type of content
            content_id: Content ID to embed
            priority: Processing priority
            scheduled_for: When to schedule processing

        Returns:
            Queue item ID
        """
        self._ensure_tenant_context(tenant_id)

        if scheduled_for is None:
            scheduled_for = datetime.now(timezone.utc)

        queue_item = {
            "tenant_id": tenant_id,
            "content_type": content_type,
            "content_id": content_id,
            "priority": priority,
            "scheduled_for": scheduled_for.isoformat()
        }

        try:
            table = self.supabase.table(self.queue_table_name)
            result = table.insert(queue_item).execute()

            if result.data:
                queue_id = result.data[0]["id"]
                logger.info(f"Queued embedding for tenant {tenant_id}, content {content_id}")
                return queue_id
            else:
                raise Exception("Failed to queue embedding")

        except Exception as e:
            logger.error(f"Failed to queue embedding: {e}")
            raise

    async def get_queue_items(
        self,
        tenant_id: str,
        limit: int = 100,
        priority: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get pending queue items for processing.

        Args:
            tenant_id: Tenant ID
            limit: Maximum items to return
            priority: Filter by priority (optional)

        Returns:
            List of queue items ready for processing
        """
        self._ensure_tenant_context(tenant_id)

        try:
            table = self.supabase.table(self.queue_table_name)
            query = table.select("*").eq("tenant_id", tenant_id)

            # Only get items that haven't started processing
            query = query.is_("processing_started_at", None)

            # Filter by priority if specified
            if priority:
                query = query.eq("priority", priority)

            # Order by priority and scheduled time
            query = query.order("priority").order("scheduled_for")

            # Limit results
            query = query.limit(limit)

            result = query.execute()

            return result.data or []

        except Exception as e:
            logger.error(f"Failed to get queue items: {e}")
            return []

    async def mark_queue_item_processing(
        self,
        queue_id: str,
        worker_id: Optional[str] = None
    ) -> bool:
        """
        Mark a queue item as being processed.

        Args:
            queue_id: Queue item ID
            worker_id: ID of the worker processing this item

        Returns:
            Success status
        """
        try:
            update_data = {
                "processing_started_at": datetime.now(timezone.utc).isoformat()
            }

            if worker_id:
                update_data["worker_id"] = worker_id

            table = self.supabase.table(self.queue_table_name)
            result = table.update(update_data).eq("id", queue_id).execute()

            return len(result.data or []) > 0

        except Exception as e:
            logger.error(f"Failed to mark queue item as processing: {e}")
            return False

    async def complete_queue_item(
        self,
        queue_id: str,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Mark a queue item as completed or failed.

        Args:
            queue_id: Queue item ID
            success: Whether processing was successful
            error_message: Error message if failed

        Returns:
            Success status
        """
        try:
            update_data = {
                "processing_completed_at": datetime.now(timezone.utc).isoformat()
            }

            if not success and error_message is not None:
                # Get current retry count
                table = self.supabase.table(self.queue_table_name)
                current = table.select("retry_count").eq("id", queue_id).execute()

                if current.data:
                    current_retry = current.data[0].get("retry_count", 0)
                    update_data["retry_count"] = current_retry + 1
                    update_data["error_message"] = error_message

            table = self.supabase.table(self.queue_table_name)
            result = table.update(update_data).eq("id", queue_id).execute()

            return len(result.data or []) > 0

        except Exception as e:
            logger.error(f"Failed to complete queue item: {e}")
            return False

    async def log_pii_protection(
        self,
        tenant_id: str,
        content_type: str,
        content_id: str,
        original_hash: str,
        sanitized_hash: str,
        pii_fields_detected: List[Dict[str, Any]],
        sanitization_method: str,
        compliance_status: str,
        reviewed_by: Optional[str] = None,
        reviewed_at: Optional[datetime] = None
    ) -> str:
        """
        Log PII protection activities for compliance tracking.

        Args:
            tenant_id: Tenant ID
            content_type: Type of content
            content_id: Content ID
            original_hash: Hash of original content
            sanitized_hash: Hash of sanitized content
            pii_fields_detected: List of detected PII fields
            sanitization_method: Method used for sanitization
            compliance_status: Compliance status
            reviewed_by: User who reviewed (if applicable)
            reviewed_at: Review timestamp (if applicable)

        Returns:
            Log entry ID
        """
        self._ensure_tenant_context(tenant_id)

        log_entry = {
            "tenant_id": tenant_id,
            "content_type": content_type,
            "content_id": content_id,
            "original_hash": original_hash,
            "sanitized_hash": sanitized_hash,
            "pii_fields_detected": pii_fields_detected,
            "sanitization_method": sanitization_method,
            "compliance_status": compliance_status
        }

        if reviewed_by:
            log_entry["reviewed_by"] = reviewed_by

        if reviewed_at:
            log_entry["reviewed_at"] = reviewed_at.isoformat()

        try:
            table = self.supabase.table(self.pii_log_table_name)
            result = table.insert(log_entry).execute()

            if result.data:
                log_id = result.data[0]["id"]
                logger.info(f"Logged PII protection for tenant {tenant_id}, content {content_id}")
                return log_id
            else:
                raise Exception("Failed to log PII protection")

        except Exception as e:
            logger.error(f"Failed to log PII protection: {e}")
            raise

    async def get_tenant_statistics(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get vector database statistics for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Dictionary with tenant statistics
        """
        self._ensure_tenant_context(tenant_id)

        try:
            # This would typically use a view or stored procedure
            # For now, we'll query the tables directly
            table = self.supabase.table(self.table_name)
            result = table.select("content_type, status").eq("tenant_id", tenant_id).execute()

            if not result.data:
                return {
                    "total_embeddings": 0,
                    "by_content_type": {},
                    "by_status": {},
                    "last_updated": None
                }

            # Aggregate statistics
            stats = {"total_embeddings": len(result.data)}
            content_type_counts = {}
            status_counts = {}

            for record in result.data:
                content_type = record.get("content_type", "unknown")
                status = record.get("status", "unknown")

                content_type_counts[content_type] = content_type_counts.get(content_type, 0) + 1
                status_counts[status] = status_counts.get(status, 0) + 1

            stats["by_content_type"] = content_type_counts  # type: ignore[assignment]
            stats["by_status"] = status_counts  # type: ignore[assignment]

            # Get last updated timestamp
            latest_result = table.select("updated_at").eq("tenant_id", tenant_id).order("updated_at", desc=True).limit(1).execute()
            if latest_result.data:
                stats["last_updated"] = latest_result.data[0].get("updated_at")

            return stats

        except Exception as e:
            logger.error(f"Failed to get tenant statistics: {e}")
            return {
                "total_embeddings": 0,
                "by_content_type": {},
                "by_status": {},
                "error": str(e)
            }

    async def cleanup_old_embeddings(
        self,
        tenant_id: str,
        older_than_days: int = 90
    ) -> int:
        """
        Clean up old embeddings for a tenant.

        Args:
            tenant_id: Tenant ID
            older_than_days: Delete embeddings older than this many days

        Returns:
            Number of embeddings deleted
        """
        self._ensure_tenant_context(tenant_id)

        try:
            from datetime import timedelta
            cutoff_date = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ) - timedelta(days=older_than_days)

            table = self.supabase.table(self.table_name)
            result = table.delete().eq("tenant_id", tenant_id).lt("created_at", cutoff_date.isoformat()).execute()

            deleted_count = len(result.data or [])
            logger.info(f"Cleaned up {deleted_count} old embeddings for tenant {tenant_id}")

            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup old embeddings: {e}")
            return 0