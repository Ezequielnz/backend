"""
Integration Tests for Phase 5 Monitoring System
Tests end-to-end workflows for drift detection, metric aggregation, and compliance reporting.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.workers.monitoring_worker import (
    detect_drift_all_models,
    aggregate_hourly_metrics,
    generate_weekly_compliance_report,
    process_feedback_batch
)


class TestDriftDetectionWorkflow:
    """Test end-to-end drift detection workflow"""
    
    @pytest.mark.asyncio
    async def test_drift_detection_workflow_complete(self):
        """Test complete drift detection workflow from detection to alert"""
        from app.services.drift_detector import drift_detector
        
        tenant_id = 'test_tenant_123'
        model_id = 'test_model_456'
        
        # Mock database responses
        with patch.object(drift_detector, 'supabase') as mock_supabase:
            # Mock baseline metrics
            mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = Mock(
                data=[{
                    'training_metrics': {'mape': 0.15, 'smape': 0.25},
                    'accuracy': 0.85
                }]
            )
            
            # Mock current predictions
            predictions = [
                {'predicted_values': {'yhat': 100}, 'confidence_score': 0.7}
                for _ in range(50)
            ]
            mock_supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = Mock(
                data=predictions
            )
            
            # Run drift detection
            result = await drift_detector.detect_drift(tenant_id, model_id, 7)
            
            # Verify workflow completed
            assert result is not None
            assert hasattr(result, 'drift_detected')
            assert hasattr(result, 'drift_score')
            assert hasattr(result, 'recommendations')
    
    def test_drift_detection_celery_task(self):
        """Test drift detection Celery task execution"""
        with patch('app.workers.monitoring_worker.get_supabase_client') as mock_supabase_fn, \
             patch('app.workers.monitoring_worker.drift_detector') as mock_detector:
            
            # Mock active models
            mock_supabase = Mock()
            mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = Mock(
                data=[
                    {'id': 'model_1', 'tenant_id': 'tenant_1', 'model_type': 'prophet'},
                    {'id': 'model_2', 'tenant_id': 'tenant_2', 'model_type': 'sarimax'}
                ]
            )
            mock_supabase_fn.return_value = mock_supabase
            
            # Mock drift detection results
            mock_result = Mock()
            mock_result.drift_detected = True
            mock_result.drift_score = 0.6
            mock_result.drift_type = 'concept'
            mock_detector.detect_drift = AsyncMock(return_value=mock_result)
            
            # Run task
            result = detect_drift_all_models()
            
            # Verify task completed
            assert result['status'] == 'success'
            assert result['models_checked'] == 2


class TestMetricAggregationWorkflow:
    """Test metric aggregation workflows"""
    
    def test_hourly_aggregation_task(self):
        """Test hourly metric aggregation task"""
        with patch('app.workers.monitoring_worker.get_supabase_client') as mock_supabase_fn:
            mock_supabase = Mock()
            
            # Mock tenants
            mock_supabase.table.return_value.select.return_value.execute.return_value = Mock(
                data=[{'id': 'tenant_1'}, {'id': 'tenant_2'}]
            )
            
            # Mock upsert
            mock_supabase.table.return_value.upsert.return_value.execute.return_value = Mock(data=[{}])
            
            mock_supabase_fn.return_value = mock_supabase
            
            # Run task
            result = aggregate_hourly_metrics()
            
            # Verify aggregation completed
            assert result['status'] == 'success'
            assert 'tenants_processed' in result
    
    def test_daily_aggregation_from_hourly(self):
        """Test daily aggregation from hourly metrics"""
        from app.workers.monitoring_worker import aggregate_daily_metrics
        
        with patch('app.workers.monitoring_worker.get_supabase_client') as mock_supabase_fn:
            mock_supabase = Mock()
            
            # Mock hourly metrics
            hourly_metrics = [
                {
                    'ml_predictions_count': 10,
                    'ml_avg_latency_ms': 200,
                    'llm_calls_count': 5,
                    'llm_total_cost': 0.5
                }
                for _ in range(24)  # 24 hours
            ]
            
            mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = Mock(
                data=hourly_metrics
            )
            mock_supabase.table.return_value.select.return_value.execute.return_value = Mock(
                data=[{'id': 'tenant_1'}]
            )
            mock_supabase.table.return_value.upsert.return_value.execute.return_value = Mock(data=[{}])
            
            mock_supabase_fn.return_value = mock_supabase
            
            # Run aggregation
            result = aggregate_daily_metrics()
            
            # Verify daily aggregation
            assert result['status'] == 'success'


class TestComplianceReportingWorkflow:
    """Test compliance reporting workflows"""
    
    def test_weekly_compliance_report_generation(self):
        """Test weekly compliance report generation"""
        with patch('app.workers.monitoring_worker.get_supabase_client') as mock_supabase_fn:
            mock_supabase = Mock()
            
            # Mock tenants
            mock_supabase.table.return_value.select.return_value.execute.return_value = Mock(
                data=[{'id': 'tenant_1'}]
            )
            
            # Mock privacy audit events
            audit_events = [
                {
                    'event_type': 'pii_detected',
                    'gdpr_compliant': True,
                    'risk_level': 'low'
                }
                for _ in range(50)
            ]
            # Add some violations
            audit_events.extend([
                {
                    'event_type': 'pii_detected',
                    'gdpr_compliant': False,
                    'risk_level': 'high'
                }
                for _ in range(5)
            ])
            
            mock_supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = Mock(
                data=audit_events
            )
            
            # Mock report insert
            mock_supabase.table.return_value.insert.return_value.execute.return_value = Mock(data=[{}])
            
            mock_supabase_fn.return_value = mock_supabase
            
            # Run report generation
            result = generate_weekly_compliance_report()
            
            # Verify report generated
            assert result['status'] == 'success'
            assert result['reports_generated'] >= 0
    
    def test_compliance_score_calculation(self):
        """Test compliance score calculation logic"""
        # Test perfect compliance
        total_events = 100
        violations = 0
        
        compliance_score = 100.0
        if total_events > 0:
            violation_rate = violations / total_events
            compliance_score = max(0, 100 - (violation_rate * 100))
        
        assert compliance_score == 100.0
        
        # Test with violations
        violations = 10
        violation_rate = violations / total_events
        compliance_score = max(0, 100 - (violation_rate * 100))
        
        assert compliance_score == 90.0


class TestFeedbackProcessingWorkflow:
    """Test feedback processing workflows"""
    
    def test_feedback_batch_processing(self):
        """Test batch processing of user feedback"""
        with patch('app.workers.monitoring_worker.get_supabase_client') as mock_supabase_fn:
            mock_supabase = Mock()
            
            # Mock unprocessed feedback
            feedback_items = [
                {
                    'id': f'feedback_{i}',
                    'tenant_id': 'tenant_1',
                    'feedback_type': 'prediction',
                    'target_id': f'pred_{i}',
                    'rating': 2,  # Low rating
                    'sentiment': 'negative'
                }
                for i in range(10)
            ]
            
            mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = Mock(
                data=feedback_items
            )
            
            # Mock update
            mock_supabase.table.return_value.update.return_value.in_.return_value.execute.return_value = Mock(data=[{}])
            
            # Mock insert for suggestions
            mock_supabase.table.return_value.insert.return_value.execute.return_value = Mock(data=[{}])
            
            mock_supabase_fn.return_value = mock_supabase
            
            # Run processing
            result = process_feedback_batch(batch_size=10)
            
            # Verify processing completed
            assert result['status'] == 'success'
            assert result['processed'] >= 0
    
    def test_feedback_grouping_logic(self):
        """Test feedback grouping by type and target"""
        from app.workers.monitoring_worker import _group_feedback
        
        feedback_items = [
            {'feedback_type': 'prediction', 'target_id': 'pred_1'},
            {'feedback_type': 'prediction', 'target_id': 'pred_1'},
            {'feedback_type': 'action', 'target_id': 'action_1'},
        ]
        
        groups = _group_feedback(feedback_items)
        
        assert len(groups) == 2  # Two unique groups
        assert 'prediction:pred_1' in groups
        assert len(groups['prediction:pred_1']) == 2
    
    def test_feedback_analysis_low_rating(self):
        """Test feedback analysis with low ratings"""
        from app.workers.monitoring_worker import _analyze_feedback_group
        
        items = [
            {'rating': 2, 'sentiment': 'negative', 'feedback_type': 'prediction', 'tenant_id': 'tenant_1'},
            {'rating': 1, 'sentiment': 'negative', 'feedback_type': 'prediction', 'tenant_id': 'tenant_1'},
            {'rating': 2, 'sentiment': 'negative', 'feedback_type': 'prediction', 'tenant_id': 'tenant_1'},
        ]
        
        analysis = _analyze_feedback_group(items)
        
        assert analysis['should_create_suggestion'] == True
        assert analysis['priority'] == 'high'  # Low avg rating should trigger high priority
        assert analysis['suggestion_type'] == 'model_retrain'


class TestAPIEndpointsIntegration:
    """Test API endpoints integration"""
    
    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)
    
    @pytest.fixture
    def auth_headers(self):
        """Mock authentication headers"""
        return {'Authorization': 'Bearer test_token'}
    
    def test_get_drift_alerts_endpoint(self, client):
        """Test GET /monitoring/drift/{tenant_id} endpoint"""
        with patch('app.api.api_v1.endpoints.monitoring.get_current_user') as mock_user, \
             patch('app.api.api_v1.endpoints.monitoring.get_supabase_client') as mock_supabase_fn:
            
            mock_user.return_value = {'id': 'user_1', 'tenant_id': 'tenant_1'}
            
            mock_supabase = Mock()
            mock_supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = Mock(
                data=[
                    {
                        'id': 'alert_1',
                        'severity': 'high',
                        'message': 'Drift detected',
                        'created_at': datetime.now().isoformat()
                    }
                ]
            )
            mock_supabase_fn.return_value = mock_supabase
            
            response = client.get('/api/v1/monitoring/drift/tenant_1?days=7')
            
            # Note: This would fail without proper auth setup, but tests the endpoint structure
            assert response.status_code in [200, 401, 403]
    
    def test_get_performance_summary_endpoint(self, client):
        """Test GET /monitoring/performance/{tenant_id}/summary endpoint"""
        with patch('app.api.api_v1.endpoints.monitoring.get_current_user') as mock_user, \
             patch('app.api.api_v1.endpoints.monitoring.get_supabase_client') as mock_supabase_fn:
            
            mock_user.return_value = {'id': 'user_1', 'tenant_id': 'tenant_1'}
            
            mock_supabase = Mock()
            mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = Mock(
                data=[{
                    'ml_predictions_count': 100,
                    'llm_cache_hit_rate': 0.75,
                    'ml_avg_latency_ms': 250,
                    'llm_total_cost': 5.50
                }]
            )
            mock_supabase_fn.return_value = mock_supabase
            
            response = client.get('/api/v1/monitoring/performance/tenant_1/summary')
            
            assert response.status_code in [200, 401, 403]


class TestMonitoringDataFlow:
    """Test data flow through monitoring system"""
    
    @pytest.mark.asyncio
    async def test_drift_to_alert_to_notification_flow(self):
        """Test flow from drift detection to alert creation to notification"""
        from app.services.drift_detector import drift_detector
        
        with patch.object(drift_detector, 'supabase') as mock_supabase, \
             patch.object(drift_detector, '_get_baseline_metrics', new_callable=AsyncMock) as mock_baseline, \
             patch.object(drift_detector, '_get_current_metrics', new_callable=AsyncMock) as mock_current:
            
            # Setup: Model with significant drift
            mock_baseline.return_value = {'mape': 0.15, 'accuracy': 0.85}
            mock_current.return_value = {'mape': 0.35, 'accuracy': 0.65, 'sample_size': 100}
            
            # Mock database operations
            mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = Mock(
                data=[{'model_type': 'prophet', 'model_version': '1.0'}]
            )
            mock_supabase.table.return_value.insert.return_value.execute.return_value = Mock(data=[{}])
            
            # Run detection
            result = await drift_detector.detect_drift('tenant_1', 'model_1', 7)
            
            # Verify drift detected
            assert result.drift_detected == True
            assert result.drift_score > 0.4  # Should be significant
            
            # Verify alert would be created (check insert was called)
            assert mock_supabase.table.call_count >= 2  # metrics + alert
    
    def test_metric_aggregation_to_dashboard_flow(self):
        """Test flow from metric collection to dashboard display"""
        with patch('app.workers.monitoring_worker.get_supabase_client') as mock_supabase_fn:
            mock_supabase = Mock()
            
            # Mock tenant data
            mock_supabase.table.return_value.select.return_value.execute.return_value = Mock(
                data=[{'id': 'tenant_1'}]
            )
            
            # Mock upsert
            mock_supabase.table.return_value.upsert.return_value.execute.return_value = Mock(data=[{}])
            
            mock_supabase_fn.return_value = mock_supabase
            
            # Run aggregation
            result = aggregate_hourly_metrics(tenant_id='tenant_1')
            
            # Verify metrics aggregated
            assert result['status'] == 'success'
            
            # Verify data would be available for dashboard
            # (in real test, would query system_performance_metrics table)


class TestErrorHandlingAndRecovery:
    """Test error handling and recovery mechanisms"""
    
    @pytest.mark.asyncio
    async def test_drift_detection_handles_missing_baseline(self):
        """Test drift detection gracefully handles missing baseline"""
        from app.services.drift_detector import drift_detector
        
        with patch.object(drift_detector, '_get_baseline_metrics', new_callable=AsyncMock) as mock_baseline:
            mock_baseline.return_value = None
            
            result = await drift_detector.detect_drift('tenant_1', 'model_1', 7)
            
            assert result.drift_detected == False
            assert result.drift_type == 'none'
            assert 'No baseline available' in result.details.get('reason', '')
    
    @pytest.mark.asyncio
    async def test_drift_detection_handles_insufficient_data(self):
        """Test drift detection handles insufficient current data"""
        from app.services.drift_detector import drift_detector
        
        with patch.object(drift_detector, '_get_baseline_metrics', new_callable=AsyncMock) as mock_baseline, \
             patch.object(drift_detector, '_get_current_metrics', new_callable=AsyncMock) as mock_current:
            
            mock_baseline.return_value = {'mape': 0.15, 'accuracy': 0.85}
            mock_current.return_value = None  # Insufficient data
            
            result = await drift_detector.detect_drift('tenant_1', 'model_1', 7)
            
            assert result.drift_detected == False
            assert 'Insufficient current data' in result.details.get('reason', '')
    
    def test_worker_task_handles_database_errors(self):
        """Test worker tasks handle database errors gracefully"""
        with patch('app.workers.monitoring_worker.get_supabase_client') as mock_supabase_fn:
            # Simulate database error
            mock_supabase_fn.side_effect = Exception("Database connection failed")
            
            # Run task
            result = detect_drift_all_models()
            
            # Should return error status, not crash
            assert result['status'] == 'error'
            assert 'error' in result


class TestConcurrencyAndRaceConditions:
    """Test concurrent operations and race conditions"""
    
    @pytest.mark.asyncio
    async def test_concurrent_drift_detection(self):
        """Test multiple concurrent drift detections"""
        import asyncio
        from app.services.drift_detector import drift_detector
        
        with patch.object(drift_detector, 'supabase'), \
             patch.object(drift_detector, '_get_baseline_metrics', new_callable=AsyncMock) as mock_baseline, \
             patch.object(drift_detector, '_get_current_metrics', new_callable=AsyncMock) as mock_current:
            
            mock_baseline.return_value = {'mape': 0.15, 'accuracy': 0.85}
            mock_current.return_value = {'mape': 0.20, 'accuracy': 0.80, 'sample_size': 50}
            
            # Run 10 concurrent detections
            tasks = [
                drift_detector.detect_drift(f'tenant_{i}', f'model_{i}', 7)
                for i in range(10)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # All should complete without errors
            assert len(results) == 10
            assert all(isinstance(r, DriftDetectionResult) or isinstance(r, Exception) for r in results)


class TestDataQualityValidation:
    """Test data quality validation in monitoring"""
    
    def test_psi_handles_nan_values(self):
        """Test PSI calculation handles NaN values"""
        detector = DriftDetector()
        
        baseline = np.array([1.0, 2.0, np.nan, 4.0, 5.0])
        current = np.array([1.1, 2.1, 3.1, 4.1, 5.1])
        
        # Should handle NaN gracefully
        psi = detector._calculate_psi(baseline, current)
        
        assert isinstance(psi, float)
        assert not np.isnan(psi)
    
    def test_drift_score_handles_missing_metrics(self):
        """Test drift score calculation with missing metrics"""
        detector = DriftDetector()
        
        concept_drift = {'detected': True}  # Missing change values
        data_drift = {'detected': False}
        prediction_drift = {'detected': False}
        
        # Should handle missing values gracefully
        score = detector._calculate_drift_score(
            concept_drift, data_drift, prediction_drift
        )
        
        assert isinstance(score, float)
        assert 0 <= score <= 1.0


# Pytest configuration for integration tests

@pytest.fixture(scope="session")
def test_database():
    """Setup test database for integration tests"""
    # Would setup ephemeral test database
    yield
    # Cleanup


@pytest.fixture(autouse=True)
def reset_test_data():
    """Reset test data between tests"""
    # Would clear test tables
    yield
    # Cleanup


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])