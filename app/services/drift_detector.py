"""
Drift Detection Service - Phase 5
Monitors model performance degradation and data distribution shifts.
Implements statistical tests and automated retraining triggers.
"""
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import numpy as np
from scipy import stats
from app.db.supabase_client import get_supabase_client
from app.core.cache_manager import cache_manager

logger = logging.getLogger(__name__)


@dataclass
class DriftDetectionResult:
    """Result of drift detection analysis"""
    drift_detected: bool
    drift_score: float
    drift_type: str
    ks_statistic: float
    psi_score: float
    details: Dict[str, Any]
    recommendations: List[str]


class DriftDetector:
    """
    Drift Detection Service
    
    Monitors model performance and data distribution for:
    - Concept drift: Changes in the relationship between features and target
    - Data drift: Changes in feature distributions
    - Prediction drift: Changes in prediction distributions
    """
    
    def __init__(self):
        self.supabase = get_supabase_client()
        self.cache_manager = cache_manager
        
        # Thresholds (configurable per tenant)
        self.default_thresholds = {
            'mape_degradation': 0.15,  # 15% increase in MAPE triggers alert
            'accuracy_degradation': 0.10,  # 10% decrease in accuracy
            'ks_statistic': 0.15,  # Kolmogorov-Smirnov test threshold
            'psi_threshold': 0.2,  # Population Stability Index threshold
            'min_samples': 30,  # Minimum samples for statistical significance
        }
    
    async def detect_drift(
        self,
        tenant_id: str,
        model_id: str,
        evaluation_period_days: int = 7
    ) -> DriftDetectionResult:
        """
        Perform comprehensive drift detection for a model.
        
        Args:
            tenant_id: Tenant identifier
            model_id: Model to evaluate
            evaluation_period_days: Days to evaluate (default 7)
            
        Returns:
            DriftDetectionResult with detection status and metrics
        """
        try:
            # Get baseline performance metrics
            baseline_metrics = await self._get_baseline_metrics(tenant_id, model_id)
            if not baseline_metrics:
                logger.warning(f"No baseline metrics found for model {model_id}")
                return self._no_drift_result("No baseline available")
            
            # Get current performance metrics
            current_metrics = await self._get_current_metrics(
                tenant_id, model_id, evaluation_period_days
            )
            if not current_metrics:
                logger.warning(f"Insufficient current data for model {model_id}")
                return self._no_drift_result("Insufficient current data")
            
            # Perform drift tests
            concept_drift = await self._detect_concept_drift(
                baseline_metrics, current_metrics
            )
            
            data_drift = await self._detect_data_drift(
                tenant_id, model_id, evaluation_period_days
            )
            
            prediction_drift = await self._detect_prediction_drift(
                tenant_id, model_id, evaluation_period_days
            )
            
            # Combine results
            drift_detected = (
                concept_drift['detected'] or 
                data_drift['detected'] or 
                prediction_drift['detected']
            )
            
            # Calculate overall drift score (0-1)
            drift_score = self._calculate_drift_score(
                concept_drift, data_drift, prediction_drift
            )
            
            # Determine primary drift type
            drift_type = self._determine_drift_type(
                concept_drift, data_drift, prediction_drift
            )
            
            # Generate recommendations
            recommendations = self._generate_recommendations(
                concept_drift, data_drift, prediction_drift, drift_score
            )
            
            result = DriftDetectionResult(
                drift_detected=drift_detected,
                drift_score=drift_score,
                drift_type=drift_type,
                ks_statistic=data_drift.get('ks_statistic', 0.0),
                psi_score=data_drift.get('psi_score', 0.0),
                details={
                    'concept_drift': concept_drift,
                    'data_drift': data_drift,
                    'prediction_drift': prediction_drift,
                    'baseline_metrics': baseline_metrics,
                    'current_metrics': current_metrics,
                },
                recommendations=recommendations
            )
            
            # Store detection results
            await self._store_drift_detection(tenant_id, model_id, result)
            
            # Create alert if drift detected
            if drift_detected:
                await self._create_drift_alert(tenant_id, model_id, result)
            
            logger.info(
                f"Drift detection completed for model {model_id}: "
                f"detected={drift_detected}, score={drift_score:.3f}, type={drift_type}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Drift detection failed for model {model_id}: {e}")
            return self._no_drift_result(f"Error: {str(e)}")
    
    async def _detect_concept_drift(
        self,
        baseline: Dict[str, Any],
        current: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Detect concept drift (performance degradation)"""
        thresholds = self.default_thresholds
        
        # Calculate performance changes
        mape_change = (
            (current['mape'] - baseline['mape']) / baseline['mape']
            if baseline.get('mape') else 0
        )
        
        accuracy_change = (
            (baseline['accuracy'] - current['accuracy']) / baseline['accuracy']
            if baseline.get('accuracy') else 0
        )
        
        # Check thresholds
        mape_degraded = mape_change > thresholds['mape_degradation']
        accuracy_degraded = accuracy_change > thresholds['accuracy_degradation']
        
        detected = mape_degraded or accuracy_degraded
        
        return {
            'detected': detected,
            'mape_change': mape_change,
            'accuracy_change': accuracy_change,
            'mape_degraded': mape_degraded,
            'accuracy_degraded': accuracy_degraded,
            'severity': 'high' if (mape_degraded and accuracy_degraded) else 'medium'
        }
    
    async def _detect_data_drift(
        self,
        tenant_id: str,
        model_id: str,
        period_days: int
    ) -> Dict[str, Any]:
        """Detect data drift using statistical tests"""
        try:
            # Get baseline and current feature distributions
            baseline_data = await self._get_baseline_features(tenant_id, model_id)
            current_data = await self._get_current_features(
                tenant_id, model_id, period_days
            )
            
            if not baseline_data or not current_data:
                return {'detected': False, 'reason': 'Insufficient data'}
            
            # Kolmogorov-Smirnov test for distribution comparison
            ks_result = stats.ks_2samp(baseline_data, current_data)
            # Type ignore for scipy stats return type
            ks_statistic: float = float(ks_result[0])  # type: ignore
            ks_pvalue: float = float(ks_result[1])  # type: ignore
            
            # Population Stability Index (PSI)
            psi_score = self._calculate_psi(baseline_data, current_data)
            
            # Check thresholds
            ks_drift = ks_statistic > self.default_thresholds['ks_statistic']
            psi_drift = psi_score > self.default_thresholds['psi_threshold']
            
            detected = ks_drift or psi_drift
            
            return {
                'detected': detected,
                'ks_statistic': ks_statistic,
                'ks_pvalue': ks_pvalue,
                'psi_score': psi_score,
                'ks_drift': ks_drift,
                'psi_drift': psi_drift,
                'severity': 'high' if (ks_drift and psi_drift) else 'medium'
            }
            
        except Exception as e:
            logger.error(f"Data drift detection failed: {e}")
            return {'detected': False, 'error': str(e)}
    
    async def _detect_prediction_drift(
        self,
        tenant_id: str,
        model_id: str,
        period_days: int
    ) -> Dict[str, Any]:
        """Detect prediction drift (changes in prediction distributions)"""
        try:
            # Get baseline and current predictions
            baseline_preds = await self._get_baseline_predictions(tenant_id, model_id)
            current_preds = await self._get_current_predictions(
                tenant_id, model_id, period_days
            )
            
            if not baseline_preds or not current_preds:
                return {'detected': False, 'reason': 'Insufficient predictions'}
            
            # Statistical comparison
            ks_result = stats.ks_2samp(baseline_preds, current_preds)
            # Type ignore for scipy stats return type
            ks_stat: float = float(ks_result[0])  # type: ignore
            ks_pval: float = float(ks_result[1])  # type: ignore
            
            # Mean and variance changes
            mean_change = abs(np.mean(current_preds) - np.mean(baseline_preds))
            var_change = abs(np.var(current_preds) - np.var(baseline_preds))
            
            detected = ks_stat > self.default_thresholds['ks_statistic']
            
            return {
                'detected': detected,
                'ks_statistic': ks_stat,
                'ks_pvalue': ks_pval,
                'mean_change': float(mean_change),
                'variance_change': float(var_change),
                'severity': 'medium' if detected else 'low'
            }
            
        except Exception as e:
            logger.error(f"Prediction drift detection failed: {e}")
            return {'detected': False, 'error': str(e)}
    
    def _calculate_psi(
        self,
        baseline: np.ndarray,
        current: np.ndarray,
        bins: int = 10
    ) -> float:
        """
        Calculate Population Stability Index (PSI)
        PSI < 0.1: No significant change
        0.1 <= PSI < 0.2: Moderate change
        PSI >= 0.2: Significant change
        """
        try:
            # Create bins based on baseline distribution
            breakpoints = np.percentile(baseline, np.linspace(0, 100, bins + 1))
            breakpoints = np.unique(breakpoints)
            
            # Calculate distributions
            baseline_dist, _ = np.histogram(baseline, bins=breakpoints)
            current_dist, _ = np.histogram(current, bins=breakpoints)
            
            # Normalize to percentages
            baseline_pct = baseline_dist / len(baseline)
            current_pct = current_dist / len(current)
            
            # Avoid division by zero
            baseline_pct = np.where(baseline_pct == 0, 0.0001, baseline_pct)
            current_pct = np.where(current_pct == 0, 0.0001, current_pct)
            
            # Calculate PSI
            psi = np.sum((current_pct - baseline_pct) * np.log(current_pct / baseline_pct))
            
            return float(psi)
            
        except Exception as e:
            logger.error(f"PSI calculation failed: {e}")
            return 0.0
    
    def _calculate_drift_score(
        self,
        concept_drift: Dict[str, Any],
        data_drift: Dict[str, Any],
        prediction_drift: Dict[str, Any]
    ) -> float:
        """Calculate overall drift score (0-1)"""
        scores = []
        
        # Concept drift contribution (40%)
        if concept_drift.get('detected'):
            concept_score = min(
                abs(concept_drift.get('mape_change', 0)) + 
                abs(concept_drift.get('accuracy_change', 0)),
                1.0
            )
            scores.append(concept_score * 0.4)
        
        # Data drift contribution (35%)
        if data_drift.get('detected'):
            data_score = min(
                data_drift.get('ks_statistic', 0) * 2 + 
                data_drift.get('psi_score', 0),
                1.0
            )
            scores.append(data_score * 0.35)
        
        # Prediction drift contribution (25%)
        if prediction_drift.get('detected'):
            pred_score = min(prediction_drift.get('ks_statistic', 0) * 2, 1.0)
            scores.append(pred_score * 0.25)
        
        return min(sum(scores), 1.0)
    
    def _determine_drift_type(
        self,
        concept_drift: Dict[str, Any],
        data_drift: Dict[str, Any],
        prediction_drift: Dict[str, Any]
    ) -> str:
        """Determine primary drift type"""
        if concept_drift.get('detected'):
            return 'concept'
        elif data_drift.get('detected'):
            return 'data'
        elif prediction_drift.get('detected'):
            return 'prediction'
        else:
            return 'none'
    
    def _generate_recommendations(
        self,
        concept_drift: Dict[str, Any],
        data_drift: Dict[str, Any],
        prediction_drift: Dict[str, Any],
        drift_score: float
    ) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        if concept_drift.get('detected'):
            if concept_drift.get('mape_degraded'):
                recommendations.append(
                    "Model retraining recommended: MAPE has degraded significantly"
                )
            if concept_drift.get('accuracy_degraded'):
                recommendations.append(
                    "Review feature engineering: Accuracy has decreased"
                )
        
        if data_drift.get('detected'):
            if data_drift.get('psi_drift'):
                recommendations.append(
                    "Data distribution has shifted significantly - consider retraining with recent data"
                )
            if data_drift.get('ks_drift'):
                recommendations.append(
                    "Feature distributions have changed - review data quality and preprocessing"
                )
        
        if prediction_drift.get('detected'):
            recommendations.append(
                "Prediction patterns have changed - monitor for business logic changes"
            )
        
        if drift_score > 0.7:
            recommendations.append(
                "CRITICAL: High drift score detected - immediate retraining recommended"
            )
        elif drift_score > 0.4:
            recommendations.append(
                "Moderate drift detected - schedule retraining within 7 days"
            )
        
        if not recommendations:
            recommendations.append("No significant drift detected - continue monitoring")
        
        return recommendations
    
    async def _get_baseline_metrics(
        self,
        tenant_id: str,
        model_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get baseline performance metrics from model training"""
        try:
            table = self.supabase.table('ml_models')
            result = table.select('training_metrics, accuracy').eq('id', model_id).execute()
            
            if not result.data:
                return None
            
            model = result.data[0]
            metrics = model.get('training_metrics', {})
            
            return {
                'mape': metrics.get('mape', 0.5),
                'smape': metrics.get('smape', 1.0),
                'mae': metrics.get('mae'),
                'rmse': metrics.get('rmse'),
                'accuracy': model.get('accuracy', 0.5)
            }
            
        except Exception as e:
            logger.error(f"Failed to get baseline metrics: {e}")
            return None
    
    async def _get_current_metrics(
        self,
        tenant_id: str,
        model_id: str,
        period_days: int
    ) -> Optional[Dict[str, Any]]:
        """Calculate current performance metrics from recent predictions"""
        try:
            # Get recent predictions with actual values
            cutoff_date = (datetime.now() - timedelta(days=period_days)).date()
            
            table = self.supabase.table('ml_predictions')
            result = table.select('predicted_values, confidence_score').eq(
                'model_id', model_id
            ).gte('prediction_date', cutoff_date.isoformat()).execute()
            
            if not result.data or len(result.data) < self.default_thresholds['min_samples']:
                return None
            
            # Calculate metrics from predictions
            # This is simplified - in production, you'd compare with actual values
            predictions = result.data
            confidences = [p.get('confidence_score', 0.5) for p in predictions]
            
            return {
                'mape': 1.0 - np.mean(confidences),  # Simplified
                'smape': 2.0 * (1.0 - np.mean(confidences)),
                'mae': None,
                'rmse': None,
                'accuracy': np.mean(confidences),
                'sample_size': len(predictions)
            }
            
        except Exception as e:
            logger.error(f"Failed to get current metrics: {e}")
            return None
    
    async def _get_baseline_features(
        self,
        tenant_id: str,
        model_id: str
    ) -> Optional[np.ndarray]:
        """Get baseline feature distributions"""
        # Simplified - would fetch from ml_features table
        return np.random.normal(0, 1, 1000)  # Placeholder
    
    async def _get_current_features(
        self,
        tenant_id: str,
        model_id: str,
        period_days: int
    ) -> Optional[np.ndarray]:
        """Get current feature distributions"""
        # Simplified - would fetch recent features
        return np.random.normal(0.1, 1.1, 1000)  # Placeholder with slight drift
    
    async def _get_baseline_predictions(
        self,
        tenant_id: str,
        model_id: str
    ) -> Optional[np.ndarray]:
        """Get baseline prediction distributions"""
        try:
            table = self.supabase.table('ml_predictions')
            result = table.select('predicted_values').eq(
                'model_id', model_id
            ).limit(1000).execute()
            
            if not result.data:
                return None
            
            predictions = [
                p.get('predicted_values', {}).get('yhat', 0)
                for p in result.data
            ]
            return np.array(predictions)
            
        except Exception as e:
            logger.error(f"Failed to get baseline predictions: {e}")
            return None
    
    async def _get_current_predictions(
        self,
        tenant_id: str,
        model_id: str,
        period_days: int
    ) -> Optional[np.ndarray]:
        """Get current prediction distributions"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=period_days)).date()
            
            table = self.supabase.table('ml_predictions')
            result = table.select('predicted_values').eq(
                'model_id', model_id
            ).gte('prediction_date', cutoff_date.isoformat()).execute()
            
            if not result.data:
                return None
            
            predictions = [
                p.get('predicted_values', {}).get('yhat', 0)
                for p in result.data
            ]
            return np.array(predictions)
            
        except Exception as e:
            logger.error(f"Failed to get current predictions: {e}")
            return None
    
    async def _store_drift_detection(
        self,
        tenant_id: str,
        model_id: str,
        result: DriftDetectionResult
    ):
        """Store drift detection results"""
        try:
            # Get model info
            model_table = self.supabase.table('ml_models')
            model_result = model_table.select('model_type, model_version').eq(
                'id', model_id
            ).execute()
            
            model_info = model_result.data[0] if model_result.data else {}
            
            # Store metrics
            metrics_data = {
                'tenant_id': tenant_id,
                'model_id': model_id,
                'model_type': model_info.get('model_type', 'unknown'),
                'model_version': model_info.get('model_version', '1.0'),
                'mape': result.details.get('current_metrics', {}).get('mape'),
                'smape': result.details.get('current_metrics', {}).get('smape'),
                'mae': result.details.get('current_metrics', {}).get('mae'),
                'rmse': result.details.get('current_metrics', {}).get('rmse'),
                'accuracy': result.details.get('current_metrics', {}).get('accuracy'),
                'drift_score': result.drift_score,
                'drift_detected': result.drift_detected,
                'drift_type': result.drift_type,
                'ks_statistic': result.ks_statistic,
                'psi_score': result.psi_score,
                'evaluation_period_start': (datetime.now() - timedelta(days=7)).isoformat(),
                'evaluation_period_end': datetime.now().isoformat(),
                'sample_size': result.details.get('current_metrics', {}).get('sample_size', 0)
            }
            
            table = self.supabase.table('model_performance_metrics')
            table.insert(metrics_data).execute()
            
        except Exception as e:
            logger.error(f"Failed to store drift detection results: {e}")
    
    async def _create_drift_alert(
        self,
        tenant_id: str,
        model_id: str,
        result: DriftDetectionResult
    ):
        """Create drift alert for monitoring"""
        try:
            severity = 'critical' if result.drift_score > 0.7 else 'high' if result.drift_score > 0.4 else 'medium'
            
            alert_data = {
                'tenant_id': tenant_id,
                'model_id': model_id,
                'alert_type': 'drift_detected',
                'severity': severity,
                'message': f"{result.drift_type.capitalize()} drift detected with score {result.drift_score:.3f}",
                'details': {
                    'drift_type': result.drift_type,
                    'drift_score': result.drift_score,
                    'recommendations': result.recommendations,
                    'metrics': result.details
                },
                'threshold_exceeded': self.default_thresholds.get('ks_statistic', 0.15),
                'current_value': result.drift_score,
                'retraining_triggered': result.drift_score > 0.7  # Auto-trigger for critical drift
            }
            
            table = self.supabase.table('drift_alerts')
            table.insert(alert_data).execute()
            
            logger.warning(
                f"Drift alert created for model {model_id}: "
                f"type={result.drift_type}, score={result.drift_score:.3f}, severity={severity}"
            )
            
        except Exception as e:
            logger.error(f"Failed to create drift alert: {e}")
    
    def _no_drift_result(self, reason: str) -> DriftDetectionResult:
        """Return a no-drift result"""
        return DriftDetectionResult(
            drift_detected=False,
            drift_score=0.0,
            drift_type='none',
            ks_statistic=0.0,
            psi_score=0.0,
            details={'reason': reason},
            recommendations=["Continue monitoring"]
        )


# Global instance
drift_detector = DriftDetector()