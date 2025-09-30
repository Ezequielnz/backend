"""
Vector Enrichment Service for ML Pipeline Integration
Phase 2: Vector Enrichment
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass

from .embedding_pipeline import EmbeddingPipeline, EmbeddingConfig
from .vector_db_service import VectorDBService, VectorSearchResult
from .pii_utils import PIIHashingUtility

logger = logging.getLogger(__name__)


@dataclass
class EnrichmentContext:
    """Context for vector enrichment operations."""
    tenant_id: str
    content_type: str
    business_context: Dict[str, Any]
    enrichment_goals: List[str]
    max_results: int = 10
    similarity_threshold: float = 0.7


@dataclass
class EnrichedPrediction:
    """ML prediction enriched with vector search results."""
    original_prediction: Dict[str, Any]
    vector_enrichments: List[Dict[str, Any]]
    enrichment_metadata: Dict[str, Any]
    confidence_boost: float
    processing_time: float


class VectorEnrichmentService:
    """
    Service for enriching ML predictions with vector-based context and insights.
    Integrates with existing ML pipeline to provide enhanced recommendations.
    """

    def __init__(self):
        self.embedding_pipeline = EmbeddingPipeline()
        self.vector_db = VectorDBService()
        self.pii_utility = PIIHashingUtility()
        self.logger = logging.getLogger(__name__)

    async def enrich_sales_prediction(
        self,
        tenant_id: str,
        prediction_data: Dict[str, Any],
        context: EnrichmentContext
    ) -> EnrichedPrediction:
        """
        Enrich sales prediction with vector-based insights.

        Args:
            tenant_id: Tenant ID
            prediction_data: Original ML prediction
            context: Enrichment context

        Returns:
            Enriched prediction with vector insights
        """
        import time
        start_time = time.time()

        try:
            # Extract relevant information from prediction
            prediction_text = self._extract_prediction_context(prediction_data)

            # Search for similar historical patterns
            similar_patterns = await self._find_similar_patterns(
                tenant_id=tenant_id,
                query_text=prediction_text,
                content_type=context.content_type,
                context=context
            )

            # Search for relevant business context
            business_insights = await self._find_business_insights(
                tenant_id=tenant_id,
                context=context
            )

            # Combine enrichments
            vector_enrichments = similar_patterns + business_insights

            # Calculate confidence boost based on enrichment quality
            confidence_boost = self._calculate_confidence_boost(
                prediction_data,
                vector_enrichments
            )

            # Create enrichment metadata
            enrichment_metadata = {
                "enrichment_timestamp": datetime.now(timezone.utc).isoformat(),
                "patterns_found": len(similar_patterns),
                "insights_found": len(business_insights),
                "total_enrichments": len(vector_enrichments),
                "enrichment_types": list(set(
                    enrichment.get("type", "unknown")
                    for enrichment in vector_enrichments
                ))
            }

            return EnrichedPrediction(
                original_prediction=prediction_data,
                vector_enrichments=vector_enrichments,
                enrichment_metadata=enrichment_metadata,
                confidence_boost=confidence_boost,
                processing_time=time.time() - start_time
            )

        except Exception as e:
            self.logger.error(f"Failed to enrich sales prediction: {e}")
            # Return original prediction with error metadata
            return EnrichedPrediction(
                original_prediction=prediction_data,
                vector_enrichments=[],
                enrichment_metadata={
                    "error": str(e),
                    "enrichment_failed": True
                },
                confidence_boost=0.0,
                processing_time=time.time() - start_time
            )

    async def enrich_anomaly_detection(
        self,
        tenant_id: str,
        anomaly_data: Dict[str, Any],
        context: EnrichmentContext
    ) -> EnrichedPrediction:
        """
        Enrich anomaly detection with vector-based context.

        Args:
            tenant_id: Tenant ID
            anomaly_data: Anomaly detection results
            context: Enrichment context

        Returns:
            Enriched anomaly detection with explanations
        """
        import time
        start_time = time.time()

        try:
            # Create anomaly description for vector search
            anomaly_description = self._create_anomaly_description(anomaly_data)

            # Search for similar anomalies and their resolutions
            similar_anomalies = await self._find_similar_anomalies(
                tenant_id=tenant_id,
                anomaly_description=anomaly_description,
                context=context
            )

            # Search for contextual business information
            contextual_insights = await self._find_contextual_insights(
                tenant_id=tenant_id,
                anomaly_data=anomaly_data,
                context=context
            )

            # Combine enrichments
            vector_enrichments = similar_anomalies + contextual_insights

            # Calculate confidence boost
            confidence_boost = self._calculate_anomaly_confidence_boost(
                anomaly_data,
                vector_enrichments
            )

            # Create enrichment metadata
            enrichment_metadata = {
                "enrichment_timestamp": datetime.now(timezone.utc).isoformat(),
                "similar_anomalies_found": len(similar_anomalies),
                "contextual_insights_found": len(contextual_insights),
                "total_enrichments": len(vector_enrichments),
                "anomaly_severity": anomaly_data.get("severity", "unknown")
            }

            return EnrichedPrediction(
                original_prediction=anomaly_data,
                vector_enrichments=vector_enrichments,
                enrichment_metadata=enrichment_metadata,
                confidence_boost=confidence_boost,
                processing_time=time.time() - start_time
            )

        except Exception as e:
            self.logger.error(f"Failed to enrich anomaly detection: {e}")
            return EnrichedPrediction(
                original_prediction=anomaly_data,
                vector_enrichments=[],
                enrichment_metadata={"error": str(e)},
                confidence_boost=0.0,
                processing_time=time.time() - start_time
            )

    def _extract_prediction_context(self, prediction_data: Dict[str, Any]) -> str:
        """Extract contextual text from prediction data for vector search."""
        context_parts = []

        # Add prediction type and date range
        pred_type = prediction_data.get("prediction_type", "unknown")
        context_parts.append(f"Prediction type: {pred_type}")

        # Add model information
        model_info = prediction_data.get("model_info", {})
        if isinstance(model_info, dict):
            model_name = model_info.get("selected_model", "unknown")
            context_parts.append(f"Model: {model_name}")

        # Add prediction values
        pred_values = prediction_data.get("predicted_values", {})
        if isinstance(pred_values, dict):
            for key, value in pred_values.items():
                context_parts.append(f"{key}: {value}")

        # Add business context if available
        business_context = prediction_data.get("business_context", {})
        if isinstance(business_context, dict):
            for key, value in business_context.items():
                context_parts.append(f"{key}: {value}")

        return " | ".join(context_parts)

    def _create_anomaly_description(self, anomaly_data: Dict[str, Any]) -> str:
        """Create descriptive text for anomaly vector search."""
        description_parts = []

        # Add anomaly type and date
        anomaly_type = anomaly_data.get("anomaly_type", "unknown")
        description_parts.append(f"Anomaly type: {anomaly_type}")

        # Add anomaly characteristics
        characteristics = anomaly_data.get("characteristics", {})
        if isinstance(characteristics, dict):
            for key, value in characteristics.items():
                description_parts.append(f"{key}: {value}")

        # Add severity and confidence
        severity = anomaly_data.get("severity", "unknown")
        confidence = anomaly_data.get("confidence_score", 0)
        description_parts.append(f"Severity: {severity}")
        description_parts.append(f"Confidence: {confidence}")

        # Add affected metrics
        affected_metrics = anomaly_data.get("affected_metrics", [])
        if affected_metrics:
            description_parts.append(f"Affected metrics: {', '.join(affected_metrics)}")

        return " | ".join(description_parts)

    async def _find_similar_patterns(
        self,
        tenant_id: str,
        query_text: str,
        content_type: str,
        context: EnrichmentContext
    ) -> List[Dict[str, Any]]:
        """Find similar historical patterns using vector search."""
        try:
            # Search for similar content
            search_results = await self.embedding_pipeline.search_similar_content(
                tenant_id=tenant_id,
                query=query_text,
                content_type=content_type,
                limit=context.max_results,
                threshold=context.similarity_threshold
            )

            # Convert search results to enrichments
            enrichments = []
            for result in search_results:
                enrichment = {
                    "type": "similar_pattern",
                    "similarity_score": result.similarity_score,
                    "content_id": result.content_id,
                    "content_type": result.content_type,
                    "metadata": result.metadata,
                    "description": f"Similar pattern found with {result.similarity_score:.2f} similarity"
                }
                enrichments.append(enrichment)

            return enrichments

        except Exception as e:
            self.logger.error(f"Failed to find similar patterns: {e}")
            return []

    async def _find_business_insights(
        self,
        tenant_id: str,
        context: EnrichmentContext
    ) -> List[Dict[str, Any]]:
        """Find relevant business insights for context."""
        try:
            # Create business context query
            business_query = self._create_business_context_query(context)

            # Search for business descriptions and related content
            business_results = await self.embedding_pipeline.search_similar_content(
                tenant_id=tenant_id,
                query=business_query,
                content_type="business_description",
                limit=context.max_results // 2,
                threshold=context.similarity_threshold * 0.8  # Lower threshold for business context
            )

            # Convert to insights
            insights = []
            for result in business_results:
                insight = {
                    "type": "business_insight",
                    "similarity_score": result.similarity_score,
                    "content_id": result.content_id,
                    "content_type": result.content_type,
                    "metadata": result.metadata,
                    "description": "Business context information"
                }
                insights.append(insight)

            return insights

        except Exception as e:
            self.logger.error(f"Failed to find business insights: {e}")
            return []

    async def _find_similar_anomalies(
        self,
        tenant_id: str,
        anomaly_description: str,
        context: EnrichmentContext
    ) -> List[Dict[str, Any]]:
        """Find similar anomalies and their resolutions."""
        try:
            # Search for similar anomaly patterns
            anomaly_results = await self.embedding_pipeline.search_similar_content(
                tenant_id=tenant_id,
                query=anomaly_description,
                content_type="anomaly_pattern",
                limit=context.max_results,
                threshold=context.similarity_threshold
            )

            # Convert to anomaly enrichments
            enrichments = []
            for result in anomaly_results:
                enrichment = {
                    "type": "similar_anomaly",
                    "similarity_score": result.similarity_score,
                    "content_id": result.content_id,
                    "content_type": result.content_type,
                    "metadata": result.metadata,
                    "description": f"Similar anomaly pattern with {result.similarity_score:.2f} similarity"
                }

                # Add resolution information if available
                resolution = result.metadata.get("resolution")
                if resolution:
                    enrichment["resolution"] = resolution
                    enrichment["description"] += f" | Resolution: {resolution}"

                enrichments.append(enrichment)

            return enrichments

        except Exception as e:
            self.logger.error(f"Failed to find similar anomalies: {e}")
            return []

    async def _find_contextual_insights(
        self,
        tenant_id: str,
        anomaly_data: Dict[str, Any],
        context: EnrichmentContext
    ) -> List[Dict[str, Any]]:
        """Find contextual insights for anomaly explanation."""
        try:
            # Create context-aware query
            context_query = self._create_context_aware_query(anomaly_data, context)

            # Search for relevant contextual information
            context_results = await self.embedding_pipeline.search_similar_content(
                tenant_id=tenant_id,
                query=context_query,
                limit=context.max_results,
                threshold=context.similarity_threshold * 0.9
            )

            # Convert to contextual insights
            insights = []
            for result in context_results:
                insight = {
                    "type": "contextual_insight",
                    "similarity_score": result.similarity_score,
                    "content_id": result.content_id,
                    "content_type": result.content_type,
                    "metadata": result.metadata,
                    "description": "Contextual information for anomaly explanation"
                }
                insights.append(insight)

            return insights

        except Exception as e:
            self.logger.error(f"Failed to find contextual insights: {e}")
            return []

    def _create_business_context_query(self, context: EnrichmentContext) -> str:
        """Create business context query for vector search."""
        query_parts = []

        # Add business context information
        for key, value in context.business_context.items():
            query_parts.append(f"{key}: {value}")

        # Add enrichment goals
        if context.enrichment_goals:
            query_parts.append(f"Goals: {', '.join(context.enrichment_goals)}")

        return " | ".join(query_parts)

    def _create_context_aware_query(
        self,
        anomaly_data: Dict[str, Any],
        context: EnrichmentContext
    ) -> str:
        """Create context-aware query for anomaly insights."""
        query_parts = []

        # Add anomaly characteristics
        characteristics = anomaly_data.get("characteristics", {})
        for key, value in characteristics.items():
            query_parts.append(f"{key}: {value}")

        # Add business context
        for key, value in context.business_context.items():
            query_parts.append(f"{key}: {value}")

        return " | ".join(query_parts)

    def _calculate_confidence_boost(
        self,
        prediction_data: Dict[str, Any],
        enrichments: List[Dict[str, Any]]
    ) -> float:
        """Calculate confidence boost based on enrichment quality."""
        if not enrichments:
            return 0.0

        # Base confidence from original prediction
        original_confidence = prediction_data.get("confidence_score", 0.5)

        # Calculate boost based on enrichment factors
        total_similarity = sum(e.get("similarity_score", 0) for e in enrichments)
        avg_similarity = total_similarity / len(enrichments)

        # Boost is proportional to average similarity, capped at 0.3
        boost = min(avg_similarity * 0.3, 0.3)

        # Apply boost to original confidence
        new_confidence = min(original_confidence + boost, 1.0)

        return new_confidence - original_confidence

    def _calculate_anomaly_confidence_boost(
        self,
        anomaly_data: Dict[str, Any],
        enrichments: List[Dict[str, Any]]
    ) -> float:
        """Calculate confidence boost for anomaly detection."""
        if not enrichments:
            return 0.0

        # Base confidence from original anomaly detection
        original_confidence = anomaly_data.get("confidence_score", 0.5)

        # Look for resolution information in enrichments
        resolution_count = sum(
            1 for e in enrichments
            if e.get("type") == "similar_anomaly" and "resolution" in e
        )

        # Boost based on available resolutions and similarity
        resolution_boost = min(resolution_count * 0.1, 0.2)

        total_similarity = sum(e.get("similarity_score", 0) for e in enrichments)
        avg_similarity = total_similarity / len(enrichments)

        similarity_boost = min(avg_similarity * 0.2, 0.2)

        total_boost = resolution_boost + similarity_boost

        # Apply boost to original confidence
        new_confidence = min(original_confidence + total_boost, 1.0)

        return new_confidence - original_confidence

    async def create_content_embeddings(
        self,
        tenant_id: str,
        content_items: List[Dict[str, Any]],
        priority: str = "medium"
    ) -> List[Dict[str, Any]]:
        """
        Create embeddings for multiple content items.

        Args:
            tenant_id: Tenant ID
            content_items: List of content items to embed
            priority: Processing priority

        Returns:
            List of embedding results
        """
        results = []

        for item in content_items:
            try:
                result = await self.embedding_pipeline.process_content(
                    tenant_id=tenant_id,
                    content=item["content"],
                    content_type=item["content_type"],
                    content_id=item["content_id"],
                    priority=priority,
                    skip_queue=True  # Process immediately for enrichment
                )

                results.append({
                    "content_id": item["content_id"],
                    "content_type": item["content_type"],
                    "success": result.success,
                    "vector_id": result.vector_id,
                    "error_message": result.error_message,
                    "processing_time": result.processing_time
                })

            except Exception as e:
                self.logger.error(f"Failed to create embedding for {item['content_id']}: {e}")
                results.append({
                    "content_id": item["content_id"],
                    "content_type": item["content_type"],
                    "success": False,
                    "vector_id": None,
                    "error_message": str(e),
                    "processing_time": 0
                })

        return results

    async def get_tenant_vector_insights(
        self,
        tenant_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get vector-based insights for a tenant.

        Args:
            tenant_id: Tenant ID
            days: Number of days to analyze

        Returns:
            Dictionary with tenant insights
        """
        try:
            # Get tenant statistics
            stats = await self.embedding_pipeline.get_tenant_embedding_stats(tenant_id)

            # Get recent search logs
            # This would need to be implemented in VectorDBService

            # Get top content types and their performance
            insights = {
                "tenant_id": tenant_id,
                "analysis_period_days": days,
                "statistics": stats,
                "top_content_types": self._get_top_content_types(stats),
                "recommendations": self._generate_recommendations(stats),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            return insights

        except Exception as e:
            self.logger.error(f"Failed to get tenant vector insights: {e}")
            return {
                "tenant_id": tenant_id,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    def _get_top_content_types(self, stats: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get top content types by usage."""
        content_types = stats.get("by_content_type", {})

        sorted_types = sorted(
            content_types.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return [
            {"content_type": ct, "count": count}
            for ct, count in sorted_types[:10]
        ]

    def _generate_recommendations(self, stats: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on statistics."""
        recommendations = []

        # Check for low embedding coverage
        total_embeddings = stats.get("total_embeddings", 0)
        if total_embeddings < 10:
            recommendations.append(
                "Consider adding more content for embedding to improve search quality"
            )

        # Check for failed embeddings
        status_counts = stats.get("by_status", {})
        failed_count = status_counts.get("failed", 0)
        if failed_count > 0:
            recommendations.append(
                f"Review {failed_count} failed embeddings for quality improvement"
            )

        # Check for PII compliance issues
        # This would need to be implemented based on PII logs

        return recommendations