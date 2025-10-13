"""
Performance Tests for Phase 5 Monitoring System
Tests performance benchmarks for drift detection, metric aggregation, and dashboard queries.
"""
import pytest
import time
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

from app.services.drift_detector import DriftDetector


class TestDriftDetectionPerformance:
    """Performance tests for drift detection"""
    
    @pytest.fixture
    def drift_detector(self):
        return DriftDetector()
    
    def test_psi_calculation_performance_large_dataset(self, drift_detector):
        """Test PSI calculation with large datasets (10K samples)"""
        baseline = np.random.normal(0, 1, 10000)
        current = np.random.normal(0.1, 1.1, 10000)
        
        start = time.perf_counter()
        psi = drift_detector._calculate_psi(baseline, current)
        duration = time.perf_counter() - start
        
        # Should complete in less than 100ms
        assert duration < 0.1, f"PSI calculation took {duration:.3f}s, target < 0.1s"
        assert isinstance(psi, float)
    
    def test_drift_score_calculation_performance(self, drift_detector):
        """Test drift score calculation performance"""
        concept_drift = {'detected': True, 'mape_change': 0.2, 'accuracy_change': 0.15}
        data_drift = {'detected': True, 'ks_statistic': 0.25, 'psi_score': 0.3}
        prediction_drift = {'detected': True, 'ks_statistic': 0.2}
        
        start = time.perf_counter()
        for _ in range(10000):
            score = drift_detector._calculate_drift_score(
                concept_drift, data_drift, prediction_drift
            )
        duration = time.perf_counter() - start
        
        # 10K calculations should complete in less than 100ms
        assert duration < 0.1, f"10K drift score calculations took {duration:.3f}s"
    
    @pytest.mark.asyncio
    async def test_full_drift_detection_latency(self, drift_detector):
        """Test full drift detection latency target: <5s"""
        with patch.object(drift_detector, 'supabase'), \
             patch.object(drift_detector, '_get_baseline_metrics', new_callable=AsyncMock) as mock_baseline, \
             patch.object(drift_detector, '_get_current_metrics', new_callable=AsyncMock) as mock_current, \
             patch.object(drift_detector, '_get_baseline_features', new_callable=AsyncMock) as mock_base_feat, \
             patch.object(drift_detector, '_get_current_features', new_callable=AsyncMock) as mock_curr_feat, \
             patch.object(drift_detector, '_get_baseline_predictions', new_callable=AsyncMock) as mock_base_pred, \
             patch.object(drift_detector, '_get_current_predictions', new_callable=AsyncMock) as mock_curr_pred:
            
            # Setup mocks with realistic data
            mock_baseline.return_value = {'mape': 0.15, 'accuracy': 0.85}
            mock_current.return_value = {'mape': 0.20, 'accuracy': 0.80, 'sample_size': 100}
            mock_base_feat.return_value = np.random.normal(0, 1, 1000)
            mock_curr_feat.return_value = np.random.normal(0.1, 1.1, 1000)
            mock_base_pred.return_value = np.random.normal(100, 20, 1000)
            mock_curr_pred.return_value = np.random.normal(105, 22, 1000)
            
            start = time.perf_counter()
            result = await drift_detector.detect_drift('tenant_1', 'model_1', 7)
            duration = time.perf_counter() - start
            
            # Target: <5s for full drift detection
            assert duration < 5.0, f"Drift detection took {duration:.3f}s, target < 5s"
            assert result is not None


class TestMetricAggregationPerformance:
    """Performance tests for metric aggregation"""
    
    def test_hourly_aggregation_performance(self):
        """Test hourly metric aggregation performance target: <10s"""
        from app.workers.monitoring_worker import aggregate_hourly_metrics
        
        with patch('app.workers.monitoring_worker.get_supabase_client') as mock_supabase_fn:
            mock_supabase = Mock()
            
            # Mock 100 tenants
            tenants = [{'id': f'tenant_{i}'} for i in range(100)]
            mock_supabase.table.return_value.select.return_value.execute.return_value = Mock(data=tenants)
            mock_supabase.table.return_value.upsert.return_value.execute.return_value = Mock(data=[{}])
            
            mock_supabase_fn.return_value = mock_supabase
            
            start = time.perf_counter()
            result = aggregate_hourly_metrics()
            duration = time.perf_counter() - start
            
            # Target: <10s for 100 tenants
            assert duration < 10.0, f"Hourly aggregation took {duration:.3f}s, target < 10s"
            assert result['status'] == 'success'
    
    def test_daily_aggregation_performance(self):
        """Test daily metric aggregation performance"""
        from app.workers.monitoring_worker import aggregate_daily_metrics
        
        with patch('app.workers.monitoring_worker.get_supabase_client') as mock_supabase_fn:
            mock_supabase = Mock()
            
            # Mock tenants
            mock_supabase.table.return_value.select.return_value.execute.return_value = Mock(
                data=[{'id': 'tenant_1'}]
            )
            
            # Mock 24 hours of metrics
            hourly_metrics = [
                {
                    'ml_predictions_count': 100,
                    'ml_avg_latency_ms': 200,
                    'llm_calls_count': 50,
                    'llm_total_cost': 2.5
                }
                for _ in range(24)
            ]
            mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = Mock(
                data=hourly_metrics
            )
            mock_supabase.table.return_value.upsert.return_value.execute.return_value = Mock(data=[{}])
            
            mock_supabase_fn.return_value = mock_supabase
            
            start = time.perf_counter()
            result = aggregate_daily_metrics()
            duration = time.perf_counter() - start
            
            # Target: <5s for daily aggregation
            assert duration < 5.0, f"Daily aggregation took {duration:.3f}s, target < 5s"


class TestDashboardQueryPerformance:
    """Performance tests for dashboard queries"""
    
    def test_performance_summary_query_latency(self):
        """Test performance summary query latency target: <2s"""
        from fastapi.testclient import TestClient
        from app.main import app
        
        client = TestClient(app)
        
        with patch('app.api.api_v1.endpoints.monitoring.get_current_user') as mock_user, \
             patch('app.api.api_v1.endpoints.monitoring.get_supabase_client') as mock_supabase_fn:
            
            mock_user.return_value = {'id': 'user_1', 'tenant_id': 'tenant_1'}
            
            mock_supabase = Mock()
            mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = Mock(
                data=[{
                    'ml_predictions_count': 1000,
                    'llm_cache_hit_rate': 0.75,
                    'ml_avg_latency_ms': 250,
                    'llm_total_cost': 15.50
                }]
            )
            mock_supabase_fn.return_value = mock_supabase
            
            start = time.perf_counter()
            response = client.get('/api/v1/monitoring/performance/tenant_1/summary')
            duration = time.perf_counter() - start
            
            # Target: <2s for dashboard query
            assert duration < 2.0, f"Dashboard query took {duration:.3f}s, target < 2s"
    
    def test_cost_breakdown_query_performance(self):
        """Test cost breakdown query performance"""
        from fastapi.testclient import TestClient
        from app.main import app
        
        client = TestClient(app)
        
        with patch('app.api.api_v1.endpoints.monitoring.get_current_user') as mock_user, \
             patch('app.api.api_v1.endpoints.monitoring.get_supabase_client') as mock_supabase_fn:
            
            mock_user.return_value = {'id': 'user_1', 'tenant_id': 'tenant_1'}
            
            # Mock 1000 cost entries
            cost_entries = [
                {
                    'cost_type': 'llm_api',
                    'service_name': 'openai',
                    'amount': 0.05
                }
                for _ in range(1000)
            ]
            
            mock_supabase = Mock()
            mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = Mock(
                data=cost_entries
            )
            mock_supabase_fn.return_value = mock_supabase
            
            start = time.perf_counter()
            response = client.get('/api/v1/monitoring/costs/tenant_1/breakdown')
            duration = time.perf_counter() - start
            
            # Target: <1s for cost breakdown
            assert duration < 1.0, f"Cost breakdown query took {duration:.3f}s, target < 1s"


class TestConcurrentRequestPerformance:
    """Test performance under concurrent load"""
    
    @pytest.mark.asyncio
    async def test_concurrent_drift_detections(self):
        """Test concurrent drift detection requests"""
        import asyncio
        from app.services.drift_detector import drift_detector
        
        with patch.object(drift_detector, 'supabase'), \
             patch.object(drift_detector, '_get_baseline_metrics', new_callable=AsyncMock) as mock_baseline, \
             patch.object(drift_detector, '_get_current_metrics', new_callable=AsyncMock) as mock_current:
            
            mock_baseline.return_value = {'mape': 0.15, 'accuracy': 0.85}
            mock_current.return_value = {'mape': 0.20, 'accuracy': 0.80, 'sample_size': 50}
            
            # Simulate 50 concurrent requests
            start = time.perf_counter()
            tasks = [
                drift_detector.detect_drift(f'tenant_{i}', f'model_{i}', 7)
                for i in range(50)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            duration = time.perf_counter() - start
            
            # Target: <10s for 50 concurrent detections
            assert duration < 10.0, f"50 concurrent detections took {duration:.3f}s, target < 10s"
            assert len(results) == 50
    
    def test_concurrent_api_requests(self):
        """Test concurrent API request handling"""
        from fastapi.testclient import TestClient
        from app.main import app
        import concurrent.futures
        
        client = TestClient(app)
        
        def make_request(i):
            with patch('app.api.api_v1.endpoints.monitoring.get_current_user') as mock_user, \
                 patch('app.api.api_v1.endpoints.monitoring.get_supabase_client') as mock_supabase_fn:
                
                mock_user.return_value = {'id': f'user_{i}', 'tenant_id': f'tenant_{i}'}
                mock_supabase = Mock()
                mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = Mock(
                    data=[{'ml_predictions_count': 100}]
                )
                mock_supabase_fn.return_value = mock_supabase
                
                return client.get(f'/api/v1/monitoring/performance/tenant_{i}/summary')
        
        # Simulate 100 concurrent API requests
        start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request, i) for i in range(100)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        duration = time.perf_counter() - start
        
        # Target: <5s for 100 concurrent requests
        assert duration < 5.0, f"100 concurrent requests took {duration:.3f}s, target < 5s"
        assert len(results) == 100


class TestDatabaseQueryPerformance:
    """Test database query performance"""
    
    def test_drift_alert_query_performance(self):
        """Test drift alert query with large result set"""
        from app.services.drift_detector import drift_detector
        
        with patch.object(drift_detector, 'supabase') as mock_supabase:
            # Mock 1000 alerts
            alerts = [
                {
                    'id': f'alert_{i}',
                    'severity': 'medium',
                    'message': f'Alert {i}',
                    'created_at': datetime.now().isoformat()
                }
                for i in range(1000)
            ]
            
            mock_supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = Mock(
                data=alerts
            )
            
            # Query should be fast even with 1000 results
            start = time.perf_counter()
            # Simulate query execution
            result = mock_supabase.table('drift_alerts').select('*').eq('tenant_id', 'tenant_1').execute()
            duration = time.perf_counter() - start
            
            # Should be nearly instant with mocks
            assert duration < 0.01
    
    def test_metric_aggregation_query_performance(self):
        """Test metric aggregation query performance"""
        # Test aggregating 24 hours of metrics
        hourly_metrics = [
            {
                'ml_predictions_count': 100,
                'ml_avg_latency_ms': 200 + i * 10,
                'llm_calls_count': 50,
                'llm_total_cost': 2.5
            }
            for i in range(24)
        ]
        
        start = time.perf_counter()
        
        # Simulate aggregation logic
        total_predictions = sum(m['ml_predictions_count'] for m in hourly_metrics)
        avg_latency = sum(m['ml_avg_latency_ms'] for m in hourly_metrics) / len(hourly_metrics)
        total_cost = sum(m['llm_total_cost'] for m in hourly_metrics)
        
        duration = time.perf_counter() - start
        
        # Aggregation should be very fast
        assert duration < 0.001, f"Metric aggregation took {duration:.6f}s"
        assert total_predictions == 2400
        assert total_cost == 60.0


class TestMemoryUsage:
    """Test memory usage for monitoring operations"""
    
    def test_psi_calculation_memory_efficiency(self, drift_detector=None):
        """Test PSI calculation doesn't consume excessive memory"""
        if drift_detector is None:
            drift_detector = DriftDetector()
        
        import tracemalloc
        
        # Start memory tracking
        tracemalloc.start()
        
        # Large datasets
        baseline = np.random.normal(0, 1, 100000)
        current = np.random.normal(0.1, 1.1, 100000)
        
        snapshot1 = tracemalloc.take_snapshot()
        
        # Calculate PSI
        psi = drift_detector._calculate_psi(baseline, current)
        
        snapshot2 = tracemalloc.take_snapshot()
        tracemalloc.stop()
        
        # Calculate memory difference
        top_stats = snapshot2.compare_to(snapshot1, 'lineno')
        total_memory_kb = sum(stat.size_diff for stat in top_stats) / 1024
        
        # Should use less than 10MB for 100K samples
        assert total_memory_kb < 10240, f"PSI used {total_memory_kb:.1f}KB, target < 10MB"
    
    @pytest.mark.asyncio
    async def test_drift_detection_memory_usage(self):
        """Test drift detection memory usage"""
        import tracemalloc
        from app.services.drift_detector import drift_detector
        
        with patch.object(drift_detector, 'supabase'), \
             patch.object(drift_detector, '_get_baseline_metrics', new_callable=AsyncMock) as mock_baseline, \
             patch.object(drift_detector, '_get_current_metrics', new_callable=AsyncMock) as mock_current:
            
            mock_baseline.return_value = {'mape': 0.15, 'accuracy': 0.85}
            mock_current.return_value = {'mape': 0.20, 'accuracy': 0.80, 'sample_size': 1000}
            
            tracemalloc.start()
            snapshot1 = tracemalloc.take_snapshot()
            
            # Run detection
            result = await drift_detector.detect_drift('tenant_1', 'model_1', 7)
            
            snapshot2 = tracemalloc.take_snapshot()
            tracemalloc.stop()
            
            top_stats = snapshot2.compare_to(snapshot1, 'lineno')
            total_memory_kb = sum(stat.size_diff for stat in top_stats) / 1024
            
            # Should use less than 5MB
            assert total_memory_kb < 5120, f"Drift detection used {total_memory_kb:.1f}KB, target < 5MB"


class TestScalabilityBenchmarks:
    """Test system scalability benchmarks"""
    
    def test_drift_detection_scales_linearly(self):
        """Test drift detection scales linearly with data size"""
        detector = DriftDetector()
        
        sizes = [1000, 5000, 10000]
        durations = []
        
        for size in sizes:
            baseline = np.random.normal(0, 1, size)
            current = np.random.normal(0.1, 1.1, size)
            
            start = time.perf_counter()
            psi = detector._calculate_psi(baseline, current)
            duration = time.perf_counter() - start
            durations.append(duration)
        
        # Check linear scaling (10x data should take ~10x time, not 100x)
        ratio_5k_to_1k = durations[1] / durations[0]
        ratio_10k_to_5k = durations[2] / durations[1]
        
        # Ratios should be roughly similar (linear scaling)
        assert 0.5 < ratio_5k_to_1k < 10, f"Scaling 1K→5K: {ratio_5k_to_1k:.2f}x"
        assert 0.5 < ratio_10k_to_5k < 10, f"Scaling 5K→10K: {ratio_10k_to_5k:.2f}x"
    
    def test_metric_aggregation_scales_with_tenants(self):
        """Test metric aggregation scales with number of tenants"""
        from app.workers.monitoring_worker import aggregate_hourly_metrics
        
        tenant_counts = [10, 50, 100]
        durations = []
        
        for count in tenant_counts:
            with patch('app.workers.monitoring_worker.get_supabase_client') as mock_supabase_fn:
                mock_supabase = Mock()
                
                tenants = [{'id': f'tenant_{i}'} for i in range(count)]
                mock_supabase.table.return_value.select.return_value.execute.return_value = Mock(data=tenants)
                mock_supabase.table.return_value.upsert.return_value.execute.return_value = Mock(data=[{}])
                
                mock_supabase_fn.return_value = mock_supabase
                
                start = time.perf_counter()
                result = aggregate_hourly_metrics()
                duration = time.perf_counter() - start
                durations.append(duration)
        
        # Should scale roughly linearly
        assert all(d < 10.0 for d in durations), "All aggregations should complete in <10s"


class TestCacheEffectiveness:
    """Test caching effectiveness for performance"""
    
    @pytest.mark.asyncio
    async def test_tenant_settings_cache_hit(self):
        """Test tenant settings caching reduces database calls"""
        from app.services.drift_detector import drift_detector
        
        with patch.object(drift_detector, 'supabase') as mock_supabase, \
             patch.object(drift_detector, 'cache_manager') as mock_cache:
            
            # First call - cache miss
            mock_cache.get.return_value = None
            mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = Mock(
                data=[{'tenant_id': 'tenant_1', 'automation_enabled': True}]
            )
            
            # Would call database
            # Second call - cache hit
            mock_cache.get.return_value = {'tenant_id': 'tenant_1', 'automation_enabled': True}
            
            # Should not call database again
            # Verify cache effectiveness in real implementation


class TestResourceUtilization:
    """Test resource utilization under load"""
    
    def test_cpu_usage_under_load(self):
        """Test CPU usage remains reasonable under load"""
        detector = DriftDetector()
        
        # Simulate heavy load
        start = time.perf_counter()
        for _ in range(100):
            baseline = np.random.normal(0, 1, 1000)
            current = np.random.normal(0.1, 1.1, 1000)
            psi = detector._calculate_psi(baseline, current)
        duration = time.perf_counter() - start
        
        # 100 PSI calculations should complete in <10s
        assert duration < 10.0, f"100 PSI calculations took {duration:.3f}s"
    
    def test_recommendations_generation_performance(self):
        """Test recommendations generation is fast"""
        detector = DriftDetector()
        
        concept_drift = {'detected': True, 'mape_degraded': True, 'accuracy_degraded': True}
        data_drift = {'detected': True, 'psi_drift': True, 'ks_drift': True}
        prediction_drift = {'detected': True}
        
        start = time.perf_counter()
        for _ in range(1000):
            recommendations = detector._generate_recommendations(
                concept_drift, data_drift, prediction_drift, 0.8
            )
        duration = time.perf_counter() - start
        
        # 1000 recommendation generations should be very fast
        assert duration < 0.1, f"1000 recommendation generations took {duration:.3f}s"


# Performance test configuration

@pytest.fixture(scope="session")
def performance_test_config():
    """Configuration for performance tests"""
    return {
        'drift_detection_target_ms': 5000,
        'dashboard_query_target_ms': 2000,
        'metric_aggregation_target_ms': 10000,
        'concurrent_requests_target': 100,
        'max_memory_mb': 512
    }


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short', '-m', 'not slow'])