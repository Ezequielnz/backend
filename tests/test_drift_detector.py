
"""
Unit Tests for Drift Detector - Phase 5
Tests drift detection algorithms, statistical tests, and alert generation.
"""
import pytest
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

from app.services.drift_detector import DriftDetector, DriftDetectionResult


class TestDriftDetector:
    """Test suite for DriftDetector service"""
    
    @pytest.fixture
    def drift_detector(self):
        """Create DriftDetector instance"""
        return DriftDetector()
    
    @pytest.fixture
    def mock_supabase(self):
        """Mock Supabase client"""
        mock = Mock()
        mock.table = Mock(return_value=mock)
        mock.select = Mock(return_value=mock)
        mock.eq = Mock(return_value=mock)
        mock.gte = Mock(return_value=mock)
        mock.lte = Mock(return_value=mock)
        mock.limit = Mock(return_value=mock)
        mock.order = Mock(return_value=mock)
        mock.execute = Mock(return_value=Mock(data=[]))
        mock.insert = Mock(return_value=mock)
        return mock
    
    # Test PSI Calculation
    
    def test_psi_calculation_no_drift(self, drift_detector):
        """Test PSI calculation with identical distributions"""
        baseline = np.random.normal(0, 1, 1000)
        current = np.random.normal(0, 1, 1000)
        
        psi = drift_detector._calculate_psi(baseline, current)
        
        # PSI should be low for similar distributions
        assert psi < 0.1, f"PSI should be < 0.1 for similar distributions, got {psi}"
    
    def test_psi_calculation_moderate_drift(self, drift_detector):
        """Test PSI calculation with moderate drift"""
        baseline = np.random.normal(0, 1, 1000)
        current = np.random.normal(0.5, 1, 1000)  # Shifted mean
        
        psi = drift_detector._calculate_psi(baseline, current)
        
        # PSI should be moderate for shifted distribution
        assert 0.1 <= psi < 0.5, f"PSI should be 0.1-0.5 for moderate drift, got {psi}"
    
    def test_psi_calculation_significant_drift(self, drift_detector):
        """Test PSI calculation with significant drift"""
        baseline = np.random.normal(0, 1, 1000)
        current = np.random.normal(2, 2, 1000)  # Shifted mean and variance
        
        psi = drift_detector._calculate_psi(baseline, current)
        
        # PSI should be high for significantly different distribution
        assert psi >= 0.2, f"PSI should be >= 0.2 for significant drift, got {psi}"
    
    # Test Drift Score Calculation
    
    def test_drift_score_no_drift(self, drift_detector):
        """Test drift score with no drift detected"""
        concept_drift = {'detected': False}
        data_drift = {'detected': False}
        prediction_drift = {'detected': False}
        
        score = drift_detector._calculate_drift_score(
            concept_drift, data_drift, prediction_drift
        )
        
        assert score == 0.0, f"Drift score should be 0 with no drift, got {score}"
    
    def test_drift_score_concept_drift_only(self, drift_detector):
        """Test drift score with only concept drift"""
        concept_drift = {
            'detected': True,
            'mape_change': 0.2,
            'accuracy_change': 0.15
        }
        data_drift = {'detected': False}
        prediction_drift = {'detected': False}
        
        score = drift_detector._calculate_drift_score(
            concept_drift, data_drift, prediction_drift
        )
        
        # Should be weighted by 0.4 (concept drift weight)
        assert 0.1 <= score <= 0.5, f"Concept drift score should be 0.1-0.5, got {score}"
    
    def test_drift_score_all_drifts(self, drift_detector):
        """Test drift score with all drift types"""
        concept_drift = {
            'detected': True,
            'mape_change': 0.3,
            'accuracy_change': 0.2
        }
        data_drift = {
            'detected': True,
            'ks_statistic': 0.25,
            'psi_score': 0.3
        }
        prediction_drift = {
            'detected': True,
            'ks_statistic': 0.2
        }
        
        score = drift_detector._calculate_drift_score(
            concept_drift, data_drift, prediction_drift
        )
        
        # Should be high with all drifts detected
        assert score >= 0.5, f"Combined drift score should be >= 0.5, got {score}"
        assert score <= 1.0, f"Drift score should not exceed 1.0, got {score}"
    
    # Test Drift Type Determination
    
    def test_determine_drift_type_concept(self, drift_detector):
        """Test drift type determination - concept drift"""
        concept_drift = {'detected': True}
        data_drift = {'detected': False}
        prediction_drift = {'detected': False}
        
        drift_type = drift_detector._determine_drift_type(
            concept_drift, data_drift, prediction_drift
        )
        
        assert drift_type == 'concept'
    
    def test_determine_drift_type_data(self, drift_detector):
        """Test drift type determination - data drift"""
        concept_drift = {'detected': False}
        data_drift = {'detected': True}
        prediction_drift = {'detected': False}
        
        drift_type = drift_detector._determine_drift_type(
            concept_drift, data_drift, prediction_drift
        )
        
        assert drift_type == 'data'
    
    def test_determine_drift_type_none(self, drift_detector):
        """Test drift type determination - no drift"""
        concept_drift = {'detected': False}
        data_drift = {'detected': False}
        prediction_drift = {'detected': False}
        
        drift_type = drift_detector._determine_drift_type(
            concept_drift, data_drift, prediction_drift
        )
        
        assert drift_type == 'none'
    
    # Test Recommendations Generation
    
    def test_generate_recommendations_no_drift(self, drift_detector):
        """Test recommendations with no drift"""
        concept_drift = {'detected': False}
        data_drift = {'detected': False}
        prediction_drift = {'detected': False}
        drift_score = 0.1
        
        recommendations = drift_detector._generate_recommendations(
            concept_drift, data_drift, prediction_drift, drift_score
        )
        
        assert len(recommendations) > 0
        assert any('No significant drift' in r for r in recommendations)
    
    def test_generate_recommendations_critical_drift(self, drift_detector):
        """Test recommendations with critical drift"""
        concept_drift = {'detected': True, 'mape_degraded': True}
        data_drift = {'detected': True, 'psi_drift': True}
        prediction_drift = {'detected': True}
        drift_score = 0.8
        
        recommendations = drift_detector._generate_recommendations(
            concept_drift, data_drift, prediction_drift, drift_score
        )
        
        assert len(recommendations) > 0
        assert any('CRITICAL' in r or 'immediate' in r.lower() for r in recommendations)
    
    def test_generate_recommendations_moderate_drift(self, drift_detector):
        """Test recommendations with moderate drift"""
        concept_drift = {'detected': False}
        data_drift = {'detected': True, 'ks_drift': True}
        prediction_drift = {'detected': False}
        drift_score = 0.5
        
        recommendations = drift_detector._generate_recommendations(
            concept_drift, data_drift, prediction_drift, drift_score
        )
        
        assert len(recommendations) > 0
        assert any('schedule' in r.lower() or 'review' in r.lower() for r in recommendations)
    
    # Test Concept Drift Detection
    
    @pytest.mark.asyncio
    async def test_detect_concept_drift_no_degradation(self, drift_detector):
        """Test concept drift detection with no degradation"""
        baseline = {'mape': 0.15, 'accuracy': 0.85}
        current = {'mape': 0.16, 'accuracy': 0.84}
        
        result = await drift_detector._detect_concept_drift(baseline, current)
        
        assert result['detected'] == False
        assert result['mape_degraded'] == False
        assert result['accuracy_degraded'] == False
    
    @pytest.mark.asyncio
    async def test_detect_concept_drift_mape_degradation(self, drift_detector):
        """Test concept drift detection with MAPE degradation"""
        baseline = {'mape': 0.15, 'accuracy': 0.85}
        current = {'mape': 0.25, 'accuracy': 0.84}  # 67% increase in MAPE
        
        result = await drift_detector._detect_concept_drift(baseline, current)
        
        assert result['detected'] == True
        assert result['mape_degraded'] == True
        assert result['mape_change'] > 0.15
    
    @pytest.mark.asyncio
    async def test_detect_concept_drift_accuracy_degradation(self, drift_detector):
        """Test concept drift detection with accuracy degradation"""
        baseline = {'mape': 0.15, 'accuracy': 0.85}
        current = {'mape': 0.16, 'accuracy': 0.70}  # 17.6% decrease in accuracy
        
        result = await drift_detector._detect_concept_drift(baseline, current)
        
        assert result['detected'] == True
        assert result['accuracy_degraded'] == True
        assert result['accuracy_change'] > 0.10
    
    # Test No Drift Result
    
    def test_no_drift_result(self, drift_detector):
        """Test no drift result generation"""
        result = drift_detector._no_drift_result("Test reason")
        
        assert isinstance(result, DriftDetectionResult)
        assert result.drift_detected == False
        assert result.drift_score == 0.0
        assert result.drift_type == 'none'
        assert 'reason' in result.details
        assert result.details['reason'] == "Test reason"
    
    # Test Alert Creation
    
    @pytest.mark.asyncio
    async def test_create_drift_alert_critical(self, drift_detector, mock_supabase):
        """Test critical drift alert creation"""
        with patch.object(drift_detector, 'supabase', mock_supabase):
            result = DriftDetectionResult(
                drift_detected=True,
                drift_score=0.8,
                drift_type='concept',
                ks_statistic=0.3,
                psi_score=0.4,
                details={'test': 'data'},
                recommendations=['Retrain immediately']
            )
            
            await drift_detector._create_drift_alert('tenant_123', 'model_456', result)
            
            # Verify alert was created
            mock_supabase.table.assert_called_with('drift_alerts')
            mock_supabase.insert.assert_called_once()
            
            # Check alert data
            call_args = mock_supabase.insert.call_args[0][0]
            assert call_args['severity'] == 'critical'
            assert call_args['retraining_triggered'] == True
    
    @pytest.mark.asyncio
    async def test_create_drift_alert_medium(self, drift_detector, mock_supabase):
        """Test medium severity drift alert creation"""
        with patch.object(drift_detector, 'supabase', mock_supabase):
            result = DriftDetectionResult(
                drift_detected=True,
                drift_score=0.3,
                drift_type='data',
                ks_statistic=0.2,
                psi_score=0.15,
                details={},
                recommendations=['Monitor closely']
            )
            
            await drift_detector._create_drift_alert('tenant_123', 'model_456', result)
            
            call_args = mock_supabase.insert.call_args[0][0]
            assert call_args['severity'] == 'medium'
            assert call_args['retraining_triggered'] == False
    
    # Test Baseline Metrics Retrieval
    
    @pytest.mark.asyncio
    async def test_get_baseline_metrics_success(self, drift_detector, mock_supabase):
        """Test successful baseline metrics retrieval"""
        mock_supabase.execute.return_value = Mock(data=[{
            'training_metrics': {
                'mape': 0.15,
                'smape': 0.25,
                'mae': 100.0,
                'rmse': 150.0
            },
            'accuracy': 0.85
        }])
        
        with patch.object(drift_detector, 'supabase', mock_supabase):
            metrics = await drift_detector._get_baseline_metrics('tenant_123', 'model_456')
        
        assert metrics is not None
        assert metrics['mape'] == 0.15
        assert metrics['accuracy'] == 0.85
    
    @pytest.mark.asyncio
    async def test_get_baseline_metrics_not_found(self, drift_detector, mock_supabase):
        """Test baseline metrics retrieval when model not found"""
        mock_supabase.execute.return_value = Mock(data=[])
        
        with patch.object(drift_detector, 'supabase', mock_supabase):
            metrics = await drift_detector._get_baseline_metrics('tenant_123', 'model_456')
        
        assert metrics is None
    
    # Test Current Metrics Calculation
    
    @pytest.mark.asyncio
    async def test_get_current_metrics_sufficient_data(self, drift_detector, mock_supabase):
        """Test current metrics with sufficient data"""
        # Mock 50 predictions
        predictions = [
            {'predicted_values': {'yhat': 100}, 'confidence_score': 0.8}
            for _ in range(50)
        ]
        mock_supabase.execute.return_value = Mock(data=predictions)
        
        with patch.object(drift_detector, 'supabase', mock_supabase):
            metrics = await drift_detector._get_current_metrics('tenant_123', 'model_456', 7)
        
        assert metrics is not None
        assert metrics['sample_size'] == 50
        assert 0 <= metrics['accuracy'] <= 1.0
    
    @pytest.mark.asyncio
    async def test_get_current_metrics_insufficient_data(self, drift_detector, mock_supabase):
        """Test current metrics with insufficient data"""
        # Mock only 10 predictions (below min_samples threshold of 30)
        predictions = [
            {'predicted_values': {'yhat': 100}, 'confidence_score': 0.8}
            for _ in range(10)
        ]
        mock_supabase.execute.return_value = Mock(data=predictions)
        
        with patch.object(drift_detector, 'supabase', mock_supabase):
            metrics = await drift_detector._get_current_metrics('tenant_123', 'model_456', 7)
        
        assert metrics is None
    
    # Test Full Drift Detection Workflow
    
    @pytest.mark.asyncio
    async def test_detect_drift_no_baseline(self, drift_detector, mock_supabase):
        """Test drift detection when no baseline exists"""
        mock_supabase.execute.return_value = Mock(data=[])
        
        with patch.object(drift_detector, 'supabase', mock_supabase):
            result = await drift_detector.detect_drift('tenant_123', 'model_456', 7)
        
        assert result.drift_detected == False
        assert result.drift_type == 'none'
        assert 'No baseline available' in result.details.get('reason', '')
    
    @pytest.mark.asyncio
    async def test_detect_drift_with_mocked_data(self, drift_detector):
        """Test full drift detection with mocked methods"""
        # Mock all internal methods
        with patch.object(drift_detector, '_get_baseline_metrics', new_callable=AsyncMock) as mock_baseline, \
             patch.object(drift_detector, '_get_current_metrics', new_callable=AsyncMock) as mock_current, \
             patch.object(drift_detector, '_detect_concept_drift', new_callable=AsyncMock) as mock_concept, \
             patch.object(drift_detector, '_detect_data_drift', new_callable=AsyncMock) as mock_data, \
             patch.object(drift_detector, '_detect_prediction_drift', new_callable=AsyncMock) as mock_pred, \
             patch.object(drift_detector, '_store_drift_detection', new_callable=AsyncMock), \
             patch.object(drift_detector, '_create_drift_alert', new_callable=AsyncMock):
            
            # Setup mocks
            mock_baseline.return_value = {'mape': 0.15, 'accuracy': 0.85}
            mock_current.return_value = {'mape': 0.25, 'accuracy': 0.75, 'sample_size': 50}
            mock_concept.return_value = {'detected': True, 'mape_degraded': True, 'severity': 'high'}
            mock_data.return_value = {'detected': False, 'ks_statistic': 0.1, 'psi_score': 0.05}
            mock_pred.return_value = {'detected': False}
            
            # Run detection
            result = await drift_detector.detect_drift('tenant_123', 'model_456', 7)
            
            # Verify result
            assert result.drift_detected == True
            assert result.drift_type == 'concept'
            assert result.drift_score > 0
            assert len(result.recommendations) > 0
    
    # Test Edge Cases
    
    def test_psi_calculation_empty_arrays(self, drift_detector):
        """Test PSI calculation with empty arrays"""
        baseline = np.array([])
        current = np.array([])
        
        psi = drift_detector._calculate_psi(baseline, current)
        
        # Should handle gracefully and return 0
        assert psi == 0.0
    
    def test_psi_calculation_single_value(self, drift_detector):
        """Test PSI calculation with single value arrays"""
        baseline = np.array([1.0])
        current = np.array([1.0])
        
        psi = drift_detector._calculate_psi(baseline, current)
        
        # Should handle gracefully
        assert isinstance(psi, float)
    
    def test_drift_score_capped_at_one(self, drift_detector):
        """Test that drift score is capped at 1.0"""
        concept_drift = {
            'detected': True,
            'mape_change': 10.0,  # Extreme change
            'accuracy_change': 10.0
        }
        data_drift = {
            'detected': True,
            'ks_statistic': 1.0,
            'psi_score': 1.0
        }
        prediction_drift = {
            'detected': True,
            'ks_statistic': 1.0
        }
        
        score = drift_detector._calculate_drift_score(
            concept_drift, data_drift, prediction_drift
        )
        
        assert score <= 1.0, f"Drift score should be capped at 1.0, got {score}"


# Integration-style tests

class TestDriftDetectorIntegration:
    """Integration tests for drift detector with database"""
    
    @pytest.mark.asyncio
    async def test_store_drift_detection_success(self):
        """Test storing drift detection results"""
        detector = DriftDetector()
        
        result = DriftDetectionResult(
            drift_detected=True,
            drift_score=0.6,
            drift_type='concept',
            ks_statistic=0.2,
            psi_score=0.25,
            details={
                'current_metrics': {'mape': 0.25, 'accuracy': 0.75, 'sample_size': 100},
                'baseline_metrics': {'mape': 0.15, 'accuracy': 0.85}
            },
            recommendations=['Review model performance']
        )
        
        # This would actually store to database in real integration test
        # For unit test, we just verify the method doesn't crash
        with patch.object(detector, 'supabase'):
            await detector._store_drift_detection('tenant_123', 'model_456', result)


# Performance tests

class TestDriftDetectorPerformance:
    """Performance tests for drift detector"""
    
    def test_psi_calculation_performance(self, drift_detector):
        """Test PSI calculation performance with large datasets"""
        import time
        
        baseline = np.random.normal(0, 1, 10000)
        current = np.random.normal(0.1, 1.1, 10000)
        
        start = time.perf_counter()
        psi = drift_detector._calculate_psi(baseline, current)
        duration = time.perf_counter() - start
        
        # Should complete in less than 100ms
        assert duration < 0.1, f"PSI calculation took {duration:.3f}s, should be < 0.1s"
        assert isinstance(psi, float)
    
    def test_drift_score_calculation_performance(self, drift_detector):
        """Test drift score calculation performance"""
        import time
        
        concept_drift = {'detected': True, 'mape_change': 0.2, 'accuracy_change': 0.15}
        data_drift = {'detected': True, 'ks_statistic': 0.25, 'psi_score': 0.3}
        prediction_drift = {'detected': True, 'ks_statistic': 0.2}
        
        start = time.perf_counter()
        for _ in range(1000):
            score = drift_detector._calculate_drift_score(
                concept_drift, data_drift, prediction_drift
            )
        duration = time.perf_counter() - start
        
        # 1000 calculations should complete in less than 10ms
        assert duration < 0.01, f"1000 drift score calculations took {duration:.3f}s"