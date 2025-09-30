"""
Tests for Phase 2: Vector Enrichment Implementation
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone
import numpy as np

from app.services.ml.pii_utils import PIIHashingUtility, PIIComplianceValidator, ComplianceStatus
from app.services.ml.vector_db_service import VectorDBService
from app.services.ml.embedding_pipeline import EmbeddingPipeline, EmbeddingConfig
from app.services.ml.vector_enrichment_service import VectorEnrichmentService, EnrichmentContext
from app.services.ml.vector_monitoring_service import VectorMonitoringService


class TestPIIHashingUtility:
    """Test PII hashing utilities."""

    def test_hash_content_generation(self):
        """Test content hashing with salt."""
        utility = PIIHashingUtility()

        content = "test content with email user@example.com"
        result = utility.hash_content(content)

        assert result.original_hash is not None
        assert result.pii_hash is not None
        assert result.salt is not None
        assert result.algorithm == 'sha256'
        assert result.timestamp is not None

    def test_pii_detection(self):
        """Test PII detection in content."""
        utility = PIIHashingUtility()

        content = "Contact user@example.com or call 555-123-4567"
        detected = utility.detect_pii(content)

        assert len(detected) > 0
        assert any(field['type'] == 'email' for field in detected)
        assert any(field['type'] == 'phone' for field in detected)

    def test_content_sanitization(self):
        """Test content sanitization."""
        utility = PIIHashingUtility()

        content = "Email: user@example.com, Phone: 555-123-4567"
        sanitized, fields = utility.sanitize_content(content, method='mask')

        assert '*' in sanitized
        assert 'user@example.com' not in sanitized
        assert '555-123-4567' not in sanitized
        assert len(fields) > 0

    def test_compliance_validation(self):
        """Test compliance validation."""
        utility = PIIHashingUtility()

        # Test with high-risk PII
        high_risk_content = "Credit card: 4532-1234-5678-9012"
        fields = utility.detect_pii(high_risk_content)
        status = utility.validate_compliance(fields, "test_tenant")

        assert status == ComplianceStatus.REVIEW_REQUIRED

        # Test with no PII
        clean_content = "This is clean content"
        fields = utility.detect_pii(clean_content)
        status = utility.validate_compliance(fields, "test_tenant")

        assert status == ComplianceStatus.COMPLIANT


class TestVectorDBService:
    """Test vector database service."""

    @pytest.mark.asyncio
    async def test_store_embedding(self):
        """Test storing vector embeddings."""
        service = VectorDBService()

        with patch.object(service.supabase.table('vector_embeddings'), 'insert') as mock_insert:
            mock_insert.return_value.execute.return_value.data = [{'id': 'test_id'}]

            vector_id = await service.store_embedding(
                tenant_id="test_tenant",
                content_type="test_type",
                content_id="test_content",
                embedding_vector=[0.1, 0.2, 0.3]
            )

            assert vector_id == 'test_id'
            mock_insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_similar(self):
        """Test vector similarity search."""
        service = VectorDBService()

        with patch.object(service.supabase.table('vector_embeddings'), 'select') as mock_select:
            mock_select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
                {
                    'id': 'test_id',
                    'content_id': 'test_content',
                    'content_type': 'test_type',
                    'embedding_vector': [0.1, 0.2, 0.3],
                    'metadata': {}
                }
            ]

            results = await service.search_similar(
                tenant_id="test_tenant",
                query_vector=[0.1, 0.2, 0.3],
                limit=5
            )

            assert len(results) > 0
            assert results[0]['content_id'] == 'test_content'

    @pytest.mark.asyncio
    async def test_queue_embedding(self):
        """Test embedding queue operations."""
        service = VectorDBService()

        with patch.object(service.supabase.table('embedding_queue'), 'insert') as mock_insert:
            mock_insert.return_value.execute.return_value.data = [{'id': 'queue_id'}]

            queue_id = await service.queue_embedding(
                tenant_id="test_tenant",
                content_type="test_type",
                content_id="test_content"
            )

            assert queue_id == 'queue_id'


class TestEmbeddingPipeline:
    """Test embedding pipeline."""

    def test_pipeline_initialization(self):
        """Test pipeline initialization."""
        config = EmbeddingConfig()
        pipeline = EmbeddingPipeline(config)

        assert pipeline.config == config
        assert pipeline.pii_utility is not None
        assert pipeline.compliance_validator is not None
        assert pipeline.vector_db is not None

    @pytest.mark.asyncio
    async def test_content_processing(self):
        """Test content processing through pipeline."""
        config = EmbeddingConfig()
        pipeline = EmbeddingPipeline(config)

        with patch.object(pipeline, '_generate_embedding') as mock_generate:
            mock_generate.return_value = [0.1, 0.2, 0.3]

            with patch.object(pipeline.vector_db, 'store_embedding') as mock_store:
                mock_store.return_value = 'vector_id'

                result = await pipeline.process_content(
                    tenant_id="test_tenant",
                    content="Test content",
                    content_type="test_type",
                    content_id="test_content"
                )

                assert result.success == True
                assert result.vector_id == 'vector_id'
                assert result.embedding_vector == [0.1, 0.2, 0.3]


class TestVectorEnrichmentService:
    """Test vector enrichment service."""

    @pytest.mark.asyncio
    async def test_sales_prediction_enrichment(self):
        """Test enriching sales predictions."""
        service = VectorEnrichmentService()

        prediction_data = {
            "prediction_type": "sales_forecast",
            "predicted_values": {"yhat": 100.0},
            "confidence_score": 0.8
        }

        context = EnrichmentContext(
            tenant_id="test_tenant",
            content_type="sales_data",
            business_context={"industry": "retail"},
            enrichment_goals=["accuracy", "insights"]
        )

        with patch.object(service.embedding_pipeline, 'search_similar_content') as mock_search:
            mock_search.return_value = []

            result = await service.enrich_sales_prediction(
                tenant_id="test_tenant",
                prediction_data=prediction_data,
                context=context
            )

            assert result.original_prediction == prediction_data
            assert result.confidence_boost >= 0
            assert result.processing_time >= 0

    @pytest.mark.asyncio
    async def test_anomaly_enrichment(self):
        """Test enriching anomaly detection."""
        service = VectorEnrichmentService()

        anomaly_data = {
            "anomaly_type": "sales_spike",
            "confidence_score": 0.9,
            "severity": "high"
        }

        context = EnrichmentContext(
            tenant_id="test_tenant",
            content_type="anomaly_data",
            business_context={"industry": "retail"},
            enrichment_goals=["explanation", "resolution"]
        )

        with patch.object(service.embedding_pipeline, 'search_similar_content') as mock_search:
            mock_search.return_value = []

            result = await service.enrich_anomaly_detection(
                tenant_id="test_tenant",
                anomaly_data=anomaly_data,
                context=context
            )

            assert result.original_prediction == anomaly_data
            assert result.confidence_boost >= 0


class TestVectorMonitoringService:
    """Test vector monitoring service."""

    def test_metrics_collection(self):
        """Test metrics collection."""
        service = VectorMonitoringService()

        # Mock metrics buffer
        service.metrics_buffer.clear()

        # Test with no metrics
        metrics = asyncio.run(service.collect_metrics("test_tenant"))
        assert metrics.tenant_id == "test_tenant"

    def test_alert_evaluation(self):
        """Test alert rule evaluation."""
        service = VectorMonitoringService()

        # Create test metrics with high error rate
        metrics = Mock()
        metrics.tenant_id = "test_tenant"
        metrics.success_count = 8
        metrics.error_count = 2  # 20% error rate

        # Check if high error rate alert triggers
        triggered = asyncio.run(service.check_alerts(metrics))

        # Should trigger high_error_rate alert
        alert_names = [alert['rule_name'] for alert in triggered]
        assert 'high_error_rate' in alert_names

    def test_governance_report_generation(self):
        """Test governance report generation."""
        service = VectorMonitoringService()

        # Mock empty metrics
        service.metrics_buffer.clear()

        report = asyncio.run(service.generate_governance_report(
            tenant_id="test_tenant",
            days=30
        ))

        assert report.tenant_id == "test_tenant"
        assert report.total_operations == 0
        assert report.pii_compliance_rate == 1.0


class TestIntegration:
    """Integration tests for Phase 2 components."""

    @pytest.mark.asyncio
    async def test_end_to_end_embedding_pipeline(self):
        """Test complete embedding pipeline."""
        # Create test content with PII
        content = "Store located at 123 Main St, contact: store@example.com, phone: 555-123-4567"

        # Process through PII utilities
        pii_utility = PIIHashingUtility()
        pii_result = pii_utility.process_content_for_embedding(
            content=content,
            content_type="business_description",
            content_id="test_store_001",
            tenant_id="test_tenant"
        )

        # Verify PII was detected and sanitized
        assert len(pii_result.pii_fields_detected) > 0
        assert pii_result.compliance_status in [ComplianceStatus.COMPLIANT, ComplianceStatus.REVIEW_REQUIRED]

        # Verify content was sanitized
        assert "store@example.com" not in pii_result.sanitized_content
        assert "555-123-4567" not in pii_result.sanitized_content

    @pytest.mark.asyncio
    async def test_vector_search_with_tenant_isolation(self):
        """Test vector search with proper tenant isolation."""
        service = VectorDBService()

        # Mock Supabase calls to verify tenant filtering
        with patch.object(service.supabase.table('vector_embeddings'), 'select') as mock_select:
            mock_select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = []

            await service.search_similar(
                tenant_id="test_tenant",
                query_vector=[0.1, 0.2, 0.3]
            )

            # Verify tenant context was set
            service.supabase.rpc.assert_called()

    def test_embedding_config_validation(self):
        """Test embedding configuration validation."""
        # Test default config
        config = EmbeddingConfig()
        assert config.model_type.value == "sentence_transformers"
        assert config.batch_size == 32
        assert config.require_compliance == True

        # Test custom config
        custom_config = EmbeddingConfig(
            model_type="openai",
            batch_size=64,
            pii_sanitization_method="remove"
        )
        assert custom_config.model_type.value == "openai"
        assert custom_config.batch_size == 64
        assert custom_config.pii_sanitization_method == "remove"


# Performance benchmarks
class TestPerformance:
    """Performance tests for Phase 2 components."""

    def test_pii_detection_performance(self):
        """Test PII detection performance."""
        utility = PIIHashingUtility()

        # Test with larger content
        large_content = "Contact information: " + "user@example.com, " * 100 + "Phone: " + "555-123-4567, " * 100

        import time
        start_time = time.time()

        fields = utility.detect_pii(large_content)

        processing_time = time.time() - start_time

        # Should process quickly (less than 1 second for this size)
        assert processing_time < 1.0
        assert len(fields) > 0

    def test_vector_similarity_performance(self):
        """Test vector similarity calculation performance."""
        service = VectorDBService()

        # Test with larger vectors
        vec1 = np.random.random(384).tolist()
        vec2 = np.random.random(384).tolist()

        import time
        start_time = time.time()

        similarity = service._cosine_similarity(vec1, vec2)

        processing_time = time.time() - start_time

        # Should be very fast
        assert processing_time < 0.1
        assert -1.0 <= similarity <= 1.0


if __name__ == "__main__":
    # Run basic tests
    pytest.main([__file__, "-v"])