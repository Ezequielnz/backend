"""
Embedding Worker for Background Processing
Phase 2: Vector Enrichment
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from app.celery_app import celery_app
from app.services.ml.embedding_pipeline import EmbeddingPipeline, EmbeddingConfig
from app.services.ml.vector_db_service import VectorDBService
from app.db.supabase_client import get_supabase_service_client

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, soft_time_limit=300, time_limit=600)
def process_embedding_queue_batch(self, tenant_id: Optional[str] = None, batch_size: int = 50) -> Dict[str, Any]:
    """
    Process a batch of embedding queue items.

    Args:
        tenant_id: Specific tenant to process (None for all)
        batch_size: Number of items to process in this batch

    Returns:
        Processing results
    """
    try:
        # Initialize services
        vector_db = VectorDBService()
        config = EmbeddingConfig()
        pipeline = EmbeddingPipeline(config)

        processed_count = 0
        success_count = 0
        error_count = 0
        errors = []

        # Get queue items
        if tenant_id:
            # Get high priority items first
            high_priority_items = asyncio.run(vector_db.get_queue_items(
                tenant_id=tenant_id,
                limit=batch_size // 2,
                priority="high"
            ))

            # Get medium priority items
            medium_priority_items = asyncio.run(vector_db.get_queue_items(
                tenant_id=tenant_id,
                limit=batch_size // 2,
                priority="medium"
            ))

            queue_items = high_priority_items + medium_priority_items
        else:
            # Process high priority items from all tenants
            queue_items = asyncio.run(vector_db.get_queue_items(
                tenant_id="",  # This would need to be implemented for multi-tenant
                limit=batch_size,
                priority="high"
            ))

        # Process each item
        for item in queue_items[:batch_size]:
            try:
                # Mark as processing
                asyncio.run(vector_db.mark_queue_item_processing(
                    queue_id=item["id"],
                    worker_id=f"worker_{self.request.id}"
                ))

                # Get content for embedding (placeholder implementation)
                content = get_content_for_embedding(
                    item["content_type"],
                    item["content_id"]
                )

                if content:
                    # Process embedding
                    result = asyncio.run(pipeline.process_content(
                        tenant_id=item["tenant_id"],
                        content=content,
                        content_type=item["content_type"],
                        content_id=item["content_id"],
                        skip_queue=True
                    ))

                    # Mark as completed
                    asyncio.run(vector_db.complete_queue_item(
                        queue_id=item["id"],
                        success=result.success,
                        error_message=result.error_message
                    ))

                    processed_count += 1
                    if result.success:
                        success_count += 1
                    else:
                        error_count += 1
                        errors.append({
                            "content_id": item["content_id"],
                            "error": result.error_message
                        })

                else:
                    # Mark as failed - no content found
                    asyncio.run(vector_db.complete_queue_item(
                        queue_id=item["id"],
                        success=False,
                        error_message="Content not found for embedding"
                    ))
                    error_count += 1
                    errors.append({
                        "content_id": item["content_id"],
                        "error": "Content not found"
                    })

            except Exception as e:
                logger.error(f"Error processing queue item {item['id']}: {e}")
                asyncio.run(vector_db.complete_queue_item(
                    queue_id=item["id"],
                    success=False,
                    error_message=str(e)
                ))
                error_count += 1
                errors.append({
                    "content_id": item["content_id"],
                    "error": str(e)
                })

        return {
            "task": "process_embedding_queue_batch",
            "tenant_id": tenant_id,
            "batch_size": batch_size,
            "processed": processed_count,
            "successful": success_count,
            "errors": error_count,
            "error_details": errors,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Embedding queue batch processing failed: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=3)


@celery_app.task(bind=True, soft_time_limit=600, time_limit=900)
def process_historical_data_embeddings(self, tenant_id: str, content_types: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Process historical data for embedding creation.

    Args:
        tenant_id: Tenant ID to process
        content_types: Types of content to process (None for all)

    Returns:
        Processing results
    """
    try:
        vector_db = VectorDBService()
        config = EmbeddingConfig()
        pipeline = EmbeddingPipeline(config)

        if content_types is None:
            content_types = [
                "product_description",
                "customer_feedback",
                "business_description"
            ]

        total_processed = 0
        total_successful = 0
        results_by_type = {}

        for content_type in content_types:
            try:
                # Get historical content for this type
                historical_items = get_historical_content(
                    tenant_id=tenant_id,
                    content_type=content_type,
                    limit=1000  # Process in batches
                )

                type_processed = 0
                type_successful = 0

                for item in historical_items:
                    try:
                        result = asyncio.run(pipeline.process_content(
                            tenant_id=tenant_id,
                            content=item["content"],
                            content_type=content_type,
                            content_id=item["id"],
                            priority="low",  # Historical data has lower priority
                            skip_queue=True
                        ))

                        type_processed += 1
                        if result.success:
                            type_successful += 1

                    except Exception as e:
                        logger.error(f"Error processing historical item {item['id']}: {e}")
                        type_processed += 1

                results_by_type[content_type] = {
                    "processed": type_processed,
                    "successful": type_successful,
                    "error_rate": (type_processed - type_successful) / type_processed if type_processed > 0 else 0
                }

                total_processed += type_processed
                total_successful += type_successful

            except Exception as e:
                logger.error(f"Error processing content type {content_type}: {e}")
                results_by_type[content_type] = {
                    "processed": 0,
                    "successful": 0,
                    "error": str(e)
                }

        return {
            "task": "process_historical_data_embeddings",
            "tenant_id": tenant_id,
            "content_types": content_types,
            "total_processed": total_processed,
            "total_successful": total_successful,
            "results_by_type": results_by_type,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Historical data embedding processing failed: {e}")
        raise self.retry(exc=e, countdown=300, max_retries=2)


@celery_app.task(bind=True, soft_time_limit=300, time_limit=600)
def cleanup_old_embeddings_task(self, tenant_id: Optional[str] = None, older_than_days: int = 90) -> Dict[str, Any]:
    """
    Clean up old embeddings.

    Args:
        tenant_id: Specific tenant (None for all)
        older_than_days: Delete embeddings older than this

    Returns:
        Cleanup results
    """
    try:
        vector_db = VectorDBService()
        pipeline = EmbeddingPipeline()

        if tenant_id:
            # Clean up specific tenant
            deleted_count = asyncio.run(pipeline.cleanup_old_embeddings(
                tenant_id=tenant_id,
                older_than_days=older_than_days
            ))

            return {
                "task": "cleanup_old_embeddings_task",
                "tenant_id": tenant_id,
                "older_than_days": older_than_days,
                "deleted_count": deleted_count,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            # This would need to be implemented for multi-tenant cleanup
            # For now, just return a placeholder
            return {
                "task": "cleanup_old_embeddings_task",
                "tenant_id": "all",
                "older_than_days": older_than_days,
                "deleted_count": 0,
                "message": "Multi-tenant cleanup not implemented",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    except Exception as e:
        logger.error(f"Embedding cleanup failed: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=3)


@celery_app.task(bind=True, soft_time_limit=300, time_limit=600)
def generate_tenant_embedding_stats(self, tenant_id: str) -> Dict[str, Any]:
    """
    Generate embedding statistics for a tenant.

    Args:
        tenant_id: Tenant ID

    Returns:
        Tenant statistics
    """
    try:
        vector_db = VectorDBService()
        pipeline = EmbeddingPipeline()

        stats = asyncio.run(pipeline.get_tenant_embedding_stats(tenant_id))

        return {
            "task": "generate_tenant_embedding_stats",
            "tenant_id": tenant_id,
            "statistics": stats,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to generate tenant embedding stats: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=3)


def get_content_for_embedding(content_type: str, content_id: str) -> Optional[str]:
    """
    Get content for embedding based on type and ID.
    This is a placeholder implementation that should be replaced with actual data fetching.
    """
    # This would need to be implemented based on your specific data sources
    # For example:
    # - Query database for product descriptions
    # - Fetch customer feedback
    # - Get business information
    # etc.

    try:
        supabase = get_supabase_service_client()

        if content_type == "product_description":
            # Get product description
            table = supabase.table("productos")
            result = table.select("nombre, descripcion").eq("id", content_id).execute()

            if result.data:
                product = result.data[0]
                name = product.get("nombre", "")
                description = product.get("descripcion", "")
                return f"{name} {description}"

        elif content_type == "customer_feedback":
            # Get customer feedback (placeholder)
            return f"Customer feedback content for {content_id}"

        elif content_type == "business_description":
            # Get business description
            table = supabase.table("negocios")
            result = table.select("nombre, descripcion").eq("id", content_id).execute()

            if result.data:
                business = result.data[0]
                name = business.get("nombre", "")
                description = business.get("descripcion", "")
                return f"{name} {description}"

        # Add more content types as needed

    except Exception as e:
        logger.error(f"Error getting content for embedding: {e}")

    return None


def get_historical_content(tenant_id: str, content_type: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Get historical content for embedding processing.
    This is a placeholder implementation.
    """
    # This would need to be implemented based on your specific data sources
    # For example:
    # - Get all products without embeddings
    # - Get all historical customer feedback
    # - Get all business information
    # etc.

    try:
        supabase = get_supabase_service_client()

        if content_type == "product_description":
            # Get products that don't have embeddings yet
            table = supabase.table("productos")
            result = table.select("id, nombre, descripcion").eq("negocio_id", tenant_id).limit(limit).execute()

            if result.data:
                return [
                    {
                        "id": product["id"],
                        "content": f"{product.get('nombre', '')} {product.get('descripcion', '')}"
                    }
                    for product in result.data
                ]

        elif content_type == "business_description":
            # Get business description
            table = supabase.table("negocios")
            result = table.select("id, nombre, descripcion").eq("id", tenant_id).limit(1).execute()

            if result.data:
                business = result.data[0]
                return [
                    {
                        "id": business["id"],
                        "content": f"{business.get('nombre', '')} {business.get('descripcion', '')}"
                    }
                ]

        # Add more content types as needed

    except Exception as e:
        logger.error(f"Error getting historical content: {e}")

    return []