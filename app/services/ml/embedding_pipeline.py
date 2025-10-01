"""
Embedding Pipeline with Compliance Validation
Phase 2: Vector Enrichment
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum

from .pii_utils import PIIHashingUtility, PIIComplianceValidator, PIIDetectionResult
from .vector_db_service import VectorDBService, VectorSearchResult
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingModelType(Enum):
    """Supported embedding model types."""
    SENTENCE_TRANSFORMERS = "sentence_transformers"
    OPENAI = "openai"
    HUGGINGFACE = "huggingface"


class ContentType(Enum):
    """Types of content that can be embedded."""
    PRODUCT_DESCRIPTION = "product_description"
    CUSTOMER_FEEDBACK = "customer_feedback"
    SALES_NOTES = "sales_notes"
    BUSINESS_DESCRIPTION = "business_description"
    INVENTORY_ITEM = "inventory_item"
    FINANCIAL_RECORD = "financial_record"


@dataclass
class EmbeddingConfig:
    """Configuration for embedding pipeline."""
    model_type: EmbeddingModelType = EmbeddingModelType.SENTENCE_TRANSFORMERS
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    batch_size: int = 32
    max_retries: int = 3
    retry_delay: float = 1.0
    pii_sanitization_method: str = "mask"
    require_compliance: bool = True
    auto_queue: bool = True


@dataclass
class EmbeddingResult:
    """Result of embedding operation."""
    success: bool
    vector_id: Optional[str]
    embedding_vector: Optional[List[float]]
    pii_result: Optional[PIIDetectionResult]
    error_message: Optional[str]
    processing_time: float
    metadata: Dict[str, Any]


class EmbeddingPipeline:
    """
    Pipeline for creating vector embeddings with PII protection and compliance validation.
    """

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        self.config = config or EmbeddingConfig()
        self.pii_utility = PIIHashingUtility()
        self.compliance_validator = PIIComplianceValidator(self.pii_utility)
        self.vector_db = VectorDBService()
        self._embedding_model = None

        # Initialize embedding model
        self._initialize_embedding_model()

    def _initialize_embedding_model(self) -> None:
        """Initialize the embedding model based on configuration."""
        try:
            if self.config.model_type == EmbeddingModelType.SENTENCE_TRANSFORMERS:
                from sentence_transformers import SentenceTransformer
                self._embedding_model = SentenceTransformer(self.config.model_name)
                logger.info(f"Initialized SentenceTransformer model: {self.config.model_name}")

            elif self.config.model_type == EmbeddingModelType.OPENAI:
                # Initialize OpenAI client (requires API key)
                from openai import OpenAI
                if not settings.OPENAI_API_KEY:
                    logger.error("OPENAI_API_KEY not configured in environment variables")
                    raise ValueError("OPENAI_API_KEY must be set to use OpenAI embeddings")
                self._embedding_model = OpenAI(api_key=settings.OPENAI_API_KEY)
                logger.info("Initialized OpenAI embedding client")

            elif self.config.model_type == EmbeddingModelType.HUGGINGFACE:
                from transformers import pipeline
                self._embedding_model = pipeline(
                    "feature-extraction",
                    model=self.config.model_name
                )
                logger.info(f"Initialized HuggingFace embedding pipeline: {self.config.model_name}")

        except Exception as e:
            logger.error(f"Failed to initialize embedding model: {e}")
            self._embedding_model = None

    def _generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats
        """
        if self._embedding_model is None:
            raise RuntimeError("Embedding model not initialized")

        try:
            if self.config.model_type == EmbeddingModelType.SENTENCE_TRANSFORMERS:
                # SentenceTransformer returns numpy array
                embedding = self._embedding_model.encode(text)
                return embedding.tolist()

            elif self.config.model_type == EmbeddingModelType.OPENAI:
                response = self._embedding_model.embeddings.create(
                    input=text,
                    model=self.config.model_name
                )
                return response.data[0].embedding

            elif self.config.model_type == EmbeddingModelType.HUGGINGFACE:
                # HuggingFace pipeline returns nested arrays
                results = self._embedding_model(text)
                # Take mean of token embeddings for sentence embedding
                import numpy as np
                embedding = np.mean(results[0], axis=0)
                return embedding.tolist()

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise

    async def process_content(
        self,
        tenant_id: str,
        content: str,
        content_type: str,
        content_id: str,
        priority: str = "medium",
        skip_queue: bool = False
    ) -> EmbeddingResult:
        """
        Process content through the complete embedding pipeline.

        Args:
            tenant_id: Tenant ID for isolation
            content: Content to embed
            content_type: Type of content
            content_id: Unique content identifier
            priority: Processing priority
            skip_queue: Skip queue and process immediately

        Returns:
            EmbeddingResult with processing details
        """
        import time
        start_time = time.time()

        try:
            # Step 1: PII Detection and Sanitization
            pii_result = self.pii_utility.process_content_for_embedding(
                content=content,
                content_type=content_type,
                content_id=content_id,
                tenant_id=tenant_id,
                sanitization_method=self.config.pii_sanitization_method
            )

            # Step 2: Compliance Validation
            compliance_result = self.compliance_validator.validate_embedding_content(
                content=pii_result.sanitized_content,
                tenant_id=tenant_id,
                content_type=content_type,
                require_compliance=self.config.require_compliance
            )

            # Check if content passes compliance
            if not compliance_result['is_valid']:
                return EmbeddingResult(
                    success=False,
                    vector_id=None,
                    embedding_vector=None,
                    pii_result=pii_result,
                    error_message=f"Compliance validation failed: {', '.join(compliance_result['recommendations'])}",
                    processing_time=time.time() - start_time,
                    metadata=compliance_result
                )

            # Step 3: Generate Embedding
            try:
                embedding_vector = self._generate_embedding(pii_result.sanitized_content)
            except Exception as e:
                return EmbeddingResult(
                    success=False,
                    vector_id=None,
                    embedding_vector=None,
                    pii_result=pii_result,
                    error_message=f"Embedding generation failed: {str(e)}",
                    processing_time=time.time() - start_time,
                    metadata={"error_type": "embedding_generation"}
                )

            # Step 4: Store in Vector Database
            if skip_queue:
                # Store immediately
                vector_id = await self.vector_db.store_embedding(
                    tenant_id=tenant_id,
                    content_type=content_type,
                    content_id=content_id,
                    embedding_vector=embedding_vector,
                    metadata={
                        "original_content_length": len(content),
                        "sanitized_content_length": len(pii_result.sanitized_content),
                        "pii_count": len(pii_result.pii_fields_detected),
                        "compliance_status": pii_result.compliance_status.value,
                        "model_type": self.config.model_type.value,
                        "model_name": self.config.model_name,
                    },
                    pii_hash=self.pii_utility.hash_content(content).pii_hash,
                    priority=priority
                )

                # Log PII protection
                await self.vector_db.log_pii_protection(
                    tenant_id=tenant_id,
                    content_type=content_type,
                    content_id=content_id,
                    original_hash=self.pii_utility.hash_content(content).original_hash,
                    sanitized_hash=self.pii_utility.hash_content(pii_result.sanitized_content).original_hash,
                    pii_fields_detected=pii_result.pii_fields_detected,
                    sanitization_method=pii_result.sanitization_method,
                    compliance_status=pii_result.compliance_status.value
                )

                return EmbeddingResult(
                    success=True,
                    vector_id=vector_id,
                    embedding_vector=embedding_vector,
                    pii_result=pii_result,
                    error_message=None,
                    processing_time=time.time() - start_time,
                    metadata={"stored_immediately": True}
                )

            else:
                # Queue for background processing
                queue_id = await self.vector_db.queue_embedding(
                    tenant_id=tenant_id,
                    content_type=content_type,
                    content_id=content_id,
                    priority=priority
                )

                return EmbeddingResult(
                    success=True,
                    vector_id=None,  # Will be set when processed
                    embedding_vector=embedding_vector,
                    pii_result=pii_result,
                    error_message=None,
                    processing_time=time.time() - start_time,
                    metadata={
                        "queued": True,
                        "queue_id": queue_id,
                        "priority": priority
                    }
                )

        except Exception as e:
            logger.error(f"Embedding pipeline failed: {e}")
            return EmbeddingResult(
                success=False,
                vector_id=None,
                embedding_vector=None,
                pii_result=None,
                error_message=str(e),
                processing_time=time.time() - start_time,
                metadata={"error_type": "pipeline_error"}
            )

    async def process_batch(
        self,
        tenant_id: str,
        items: List[Dict[str, Any]],
        skip_queue: bool = False
    ) -> List[EmbeddingResult]:
        """
        Process multiple items in batch.

        Args:
            tenant_id: Tenant ID
            items: List of content items to process
            skip_queue: Skip queue and process immediately

        Returns:
            List of EmbeddingResults
        """
        results = []

        for item in items:
            result = await self.process_content(
                tenant_id=tenant_id,
                content=item["content"],
                content_type=item["content_type"],
                content_id=item["content_id"],
                priority=item.get("priority", "medium"),
                skip_queue=skip_queue
            )
            results.append(result)

        return results

    async def search_similar_content(
        self,
        tenant_id: str,
        query: str,
        content_type: Optional[str] = None,
        limit: int = 10,
        threshold: float = 0.7
    ) -> List[VectorSearchResult]:
        """
        Search for similar content using vector similarity.

        Args:
            tenant_id: Tenant ID
            query: Search query
            content_type: Filter by content type (optional)
            limit: Maximum results
            threshold: Similarity threshold

        Returns:
            List of similar content results
        """
        # Generate embedding for query
        query_embedding = self._generate_embedding(query)

        # Search vector database
        results = await self.vector_db.search_similar(
            tenant_id=tenant_id,
            query_vector=query_embedding,
            content_type=content_type,
            limit=limit,
            threshold=threshold
        )

        return results

    async def get_tenant_embedding_stats(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get embedding statistics for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Dictionary with tenant statistics
        """
        return await self.vector_db.get_tenant_statistics(tenant_id)

    async def cleanup_old_embeddings(
        self,
        tenant_id: str,
        older_than_days: int = 90
    ) -> int:
        """
        Clean up old embeddings for a tenant.

        Args:
            tenant_id: Tenant ID
            older_than_days: Delete embeddings older than this

        Returns:
            Number of embeddings deleted
        """
        return await self.vector_db.cleanup_old_embeddings(tenant_id, older_than_days)


class BackgroundEmbeddingProcessor:
    """
    Background processor for handling embedding queue.
    Processes queued embeddings with priority-based scheduling.
    """

    def __init__(self, embedding_pipeline: EmbeddingPipeline):
        self.pipeline = embedding_pipeline
        self.vector_db = VectorDBService()
        self.is_running = False
        self.logger = logging.getLogger(__name__)

    async def start_processing(self, tenant_id: Optional[str] = None) -> None:
        """
        Start background processing of embedding queue.

        Args:
            tenant_id: Specific tenant to process (None for all)
        """
        self.is_running = True

        while self.is_running:
            try:
                # Get queue items
                if tenant_id:
                    items = await self.vector_db.get_queue_items(
                        tenant_id=tenant_id,
                        limit=10,
                        priority="high"
                    )
                    # Also get medium priority items
                    medium_items = await self.vector_db.get_queue_items(
                        tenant_id=tenant_id,
                        limit=20,
                        priority="medium"
                    )
                    items.extend(medium_items)
                else:
                    # Process high priority items first
                    items = await self.vector_db.get_queue_items(
                        tenant_id="",  # This won't work with current implementation
                        limit=50,
                        priority="high"
                    )

                if not items:
                    await asyncio.sleep(5)  # Wait 5 seconds before checking again
                    continue

                # Process items
                for item in items:
                    try:
                        # Mark as processing
                        await self.vector_db.mark_queue_item_processing(
                            queue_id=item["id"],
                            worker_id="background_processor"
                        )

                        # Get content (this would need to be implemented based on content_type)
                        content = await self._get_content_for_embedding(
                            item["content_type"],
                            item["content_id"]
                        )

                        if content:
                            # Process embedding
                            result = await self.pipeline.process_content(
                                tenant_id=item["tenant_id"],
                                content=content,
                                content_type=item["content_type"],
                                content_id=item["content_id"],
                                skip_queue=True  # Process immediately
                            )

                            # Mark as completed
                            await self.vector_db.complete_queue_item(
                                queue_id=item["id"],
                                success=result.success,
                                error_message=result.error_message
                            )

                            if result.success:
                                self.logger.info(f"Processed embedding for {item['content_id']}")
                            else:
                                self.logger.error(f"Failed to process embedding for {item['content_id']}: {result.error_message}")

                    except Exception as e:
                        self.logger.error(f"Error processing queue item {item['id']}: {e}")
                        await self.vector_db.complete_queue_item(
                            queue_id=item["id"],
                            success=False,
                            error_message=str(e)
                        )

                # Small delay between batches
                await asyncio.sleep(1)

            except Exception as e:
                self.logger.error(f"Background processor error: {e}")
                await asyncio.sleep(10)  # Wait longer on error

    async def stop_processing(self) -> None:
        """Stop background processing."""
        self.is_running = False

    async def _get_content_for_embedding(
        self,
        content_type: str,
        content_id: str
    ) -> Optional[str]:
        """
        Get content for embedding based on type and ID.
        This is a placeholder - implementation depends on your data sources.
        """
        # This would need to be implemented based on your specific data sources
        # For example:
        # - Query database for product descriptions
        # - Fetch customer feedback
        # - Get business information
        # etc.

        # For now, return a placeholder
        return f"Content for {content_type} with ID {content_id}"