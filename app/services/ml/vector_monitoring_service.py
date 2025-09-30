"""
Vector Monitoring and Governance Service
Phase 2: Vector Enrichment
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from collections import defaultdict, deque
import json
import smtplib
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart

from .vector_db_service import VectorDBService
from .embedding_pipeline import EmbeddingPipeline
from .pii_utils import PIIComplianceValidator, PIIHashingUtility

logger = logging.getLogger(__name__)


@dataclass
class VectorMetrics:
    """Metrics for vector operations monitoring."""
    timestamp: datetime
    tenant_id: str
    operation_type: str
    success_count: int
    error_count: int
    avg_processing_time: float
    pii_violations: int
    total_embeddings: int
    search_queries: int
    cache_hit_rate: float


@dataclass
class AlertRule:
    """Alert rule configuration."""
    name: str
    condition: str  # e.g., "error_rate > 0.1", "pii_violations > 5"
    threshold: float
    severity: str  # "low", "medium", "high", "critical"
    notification_channels: List[str]  # "email", "slack", "webhook"
    cooldown_minutes: int = 60
    enabled: bool = True


@dataclass
class GovernanceReport:
    """Governance report for compliance and audit."""
    tenant_id: str
    report_period: Tuple[datetime, datetime]
    total_operations: int
    pii_compliance_rate: float
    data_quality_score: float
    privacy_breaches: int
    recommendations: List[str]
    generated_at: datetime


class VectorMonitoringService:
    """
    Service for monitoring and governance of vector operations.
    Provides metrics collection, alerting, and compliance reporting.
    """

    def __init__(self):
        self.vector_db = VectorDBService()
        self.embedding_pipeline = EmbeddingPipeline()
        self.pii_validator = PIIComplianceValidator(PIIHashingUtility())

        # Metrics storage
        self.metrics_buffer = deque(maxlen=10000)
        self.alert_rules = self._initialize_default_alert_rules()

        # Alert tracking to prevent spam
        self.last_alert_times = defaultdict(lambda: datetime.min.replace(tzinfo=timezone.utc))

        # Configuration
        self.metrics_collection_interval = 300  # 5 minutes
        self.report_generation_interval = 86400  # 24 hours

        self.logger = logging.getLogger(__name__)

    def _initialize_default_alert_rules(self) -> List[AlertRule]:
        """Initialize default alert rules for vector operations."""
        return [
            AlertRule(
                name="high_error_rate",
                condition="error_rate > 0.1",
                threshold=0.1,
                severity="medium",
                notification_channels=["email"],
                cooldown_minutes=30
            ),
            AlertRule(
                name="pii_violations",
                condition="pii_violations > 5",
                threshold=5,
                severity="high",
                notification_channels=["email", "slack"],
                cooldown_minutes=15
            ),
            AlertRule(
                name="low_cache_hit_rate",
                condition="cache_hit_rate < 0.3",
                threshold=0.3,
                severity="low",
                notification_channels=["email"],
                cooldown_minutes=60
            ),
            AlertRule(
                name="embedding_processing_lag",
                condition="avg_processing_time > 300",
                threshold=300,
                severity="medium",
                notification_channels=["email"],
                cooldown_minutes=45
            )
        ]

    async def collect_metrics(self, tenant_id: Optional[str] = None) -> VectorMetrics:
        """
        Collect current metrics for vector operations.

        Args:
            tenant_id: Specific tenant (None for all tenants)

        Returns:
            Current metrics
        """
        try:
            if tenant_id:
                # Get metrics for specific tenant
                stats = await self.embedding_pipeline.get_tenant_embedding_stats(tenant_id)

                # Calculate derived metrics
                total_operations = stats.get("total_embeddings", 0)
                status_counts = stats.get("by_status", {})

                success_count = status_counts.get("completed", 0)
                error_count = status_counts.get("failed", 0)
                error_rate = error_count / total_operations if total_operations > 0 else 0

                # Get recent search logs (placeholder)
                search_queries = 0
                cache_hit_rate = 0.0

                # Get average processing time (placeholder)
                avg_processing_time = 0.0

                # Get PII violations (placeholder)
                pii_violations = 0

                metrics = VectorMetrics(
                    timestamp=datetime.now(timezone.utc),
                    tenant_id=tenant_id,
                    operation_type="vector_operations",
                    success_count=success_count,
                    error_count=error_count,
                    avg_processing_time=avg_processing_time,
                    pii_violations=pii_violations,
                    total_embeddings=total_operations,
                    search_queries=search_queries,
                    cache_hit_rate=cache_hit_rate
                )

                self.metrics_buffer.append(metrics)
                return metrics

            else:
                # Aggregate metrics across all tenants (placeholder)
                # This would require querying all tenants
                return VectorMetrics(
                    timestamp=datetime.now(timezone.utc),
                    tenant_id="all",
                    operation_type="aggregate",
                    success_count=0,
                    error_count=0,
                    avg_processing_time=0.0,
                    pii_violations=0,
                    total_embeddings=0,
                    search_queries=0,
                    cache_hit_rate=0.0
                )

        except Exception as e:
            self.logger.error(f"Failed to collect metrics: {e}")
            raise

    async def check_alerts(self, metrics: VectorMetrics) -> List[Dict[str, Any]]:
        """
        Check if any alert rules are triggered.

        Args:
            metrics: Current metrics to evaluate

        Returns:
            List of triggered alerts
        """
        triggered_alerts = []

        for rule in self.alert_rules:
            if not rule.enabled:
                continue

            # Check cooldown period
            last_alert = self.last_alert_times[rule.name]
            cooldown_end = last_alert + timedelta(minutes=rule.cooldown_minutes)
            if datetime.now(timezone.utc) < cooldown_end:
                continue

            # Evaluate rule condition
            if self._evaluate_alert_condition(rule, metrics):
                alert = {
                    "rule_name": rule.name,
                    "severity": rule.severity,
                    "condition": rule.condition,
                    "threshold": rule.threshold,
                    "current_value": self._get_metric_value(rule.condition, metrics),
                    "tenant_id": metrics.tenant_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "notification_channels": rule.notification_channels
                }

                triggered_alerts.append(alert)

                # Update last alert time
                self.last_alert_times[rule.name] = datetime.now(timezone.utc)

                # Send notifications
                await self._send_alert_notifications(alert, rule)

        return triggered_alerts

    def _evaluate_alert_condition(self, rule: AlertRule, metrics: VectorMetrics) -> bool:
        """Evaluate if an alert condition is met."""
        try:
            # Simple condition evaluation (can be extended)
            if "error_rate" in rule.condition:
                error_rate = metrics.error_count / max(metrics.success_count + metrics.error_count, 1)
                threshold = rule.threshold
                return error_rate > threshold

            elif "pii_violations" in rule.condition:
                return metrics.pii_violations > rule.threshold

            elif "cache_hit_rate" in rule.condition:
                return metrics.cache_hit_rate < rule.threshold

            elif "avg_processing_time" in rule.condition:
                return metrics.avg_processing_time > rule.threshold

            return False

        except Exception as e:
            self.logger.error(f"Error evaluating alert condition {rule.condition}: {e}")
            return False

    def _get_metric_value(self, condition: str, metrics: VectorMetrics) -> float:
        """Extract metric value from condition string."""
        if "error_rate" in condition:
            return metrics.error_count / max(metrics.success_count + metrics.error_count, 1)
        elif "pii_violations" in condition:
            return float(metrics.pii_violations)
        elif "cache_hit_rate" in condition:
            return metrics.cache_hit_rate
        elif "avg_processing_time" in condition:
            return metrics.avg_processing_time
        return 0.0

    async def _send_alert_notifications(self, alert: Dict[str, Any], rule: AlertRule) -> None:
        """Send alert notifications through configured channels."""
        try:
            for channel in rule.notification_channels:
                if channel == "email":
                    await self._send_email_alert(alert)
                elif channel == "slack":
                    await self._send_slack_alert(alert)
                elif channel == "webhook":
                    await self._send_webhook_alert(alert)

        except Exception as e:
            self.logger.error(f"Failed to send alert notifications: {e}")

    async def _send_email_alert(self, alert: Dict[str, Any]) -> None:
        """Send alert via email."""
        try:
            # This is a placeholder for email sending
            # In production, you'd use a proper email service
            msg = MimeText(f"Vector Alert: {alert['rule_name']}\n\n{json.dumps(alert, indent=2)}")
            msg['Subject'] = f"Vector Alert: {alert['rule_name']}"
            msg['From'] = "vector-monitor@example.com"
            msg['To'] = "admin@example.com"

            # Placeholder for actual email sending
            self.logger.info(f"Email alert would be sent: {alert['rule_name']}")

        except Exception as e:
            self.logger.error(f"Failed to send email alert: {e}")

    async def _send_slack_alert(self, alert: Dict[str, Any]) -> None:
        """Send alert via Slack."""
        try:
            # Placeholder for Slack webhook
            self.logger.info(f"Slack alert would be sent: {alert['rule_name']}")
        except Exception as e:
            self.logger.error(f"Failed to send Slack alert: {e}")

    async def _send_webhook_alert(self, alert: Dict[str, Any]) -> None:
        """Send alert via webhook."""
        try:
            # Placeholder for webhook
            self.logger.info(f"Webhook alert would be sent: {alert['rule_name']}")
        except Exception as e:
            self.logger.error(f"Failed to send webhook alert: {e}")

    async def generate_governance_report(
        self,
        tenant_id: str,
        days: int = 30
    ) -> GovernanceReport:
        """
        Generate governance report for compliance and audit.

        Args:
            tenant_id: Tenant ID
            days: Number of days to include in report

        Returns:
            Governance report
        """
        try:
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days)

            # Collect metrics for the period
            period_metrics = [
                m for m in self.metrics_buffer
                if m.tenant_id == tenant_id and start_date <= m.timestamp <= end_date
            ]

            # Calculate compliance metrics
            total_operations = len(period_metrics)
            pii_violations = sum(m.pii_violations for m in period_metrics)

            # Calculate PII compliance rate
            pii_compliance_rate = 1.0 - (pii_violations / total_operations) if total_operations > 0 else 1.0

            # Calculate data quality score (placeholder)
            avg_error_rate = sum(
                m.error_count / max(m.success_count + m.error_count, 1)
                for m in period_metrics
            ) / len(period_metrics) if period_metrics else 0

            data_quality_score = max(0, 1.0 - avg_error_rate)

            # Generate recommendations
            recommendations = self._generate_governance_recommendations(
                period_metrics,
                pii_compliance_rate,
                data_quality_score
            )

            return GovernanceReport(
                tenant_id=tenant_id,
                report_period=(start_date, end_date),
                total_operations=total_operations,
                pii_compliance_rate=pii_compliance_rate,
                data_quality_score=data_quality_score,
                privacy_breaches=pii_violations,
                recommendations=recommendations,
                generated_at=datetime.now(timezone.utc)
            )

        except Exception as e:
            self.logger.error(f"Failed to generate governance report: {e}")
            raise

    def _generate_governance_recommendations(
        self,
        metrics: List[VectorMetrics],
        pii_compliance_rate: float,
        data_quality_score: float
    ) -> List[str]:
        """Generate recommendations based on metrics."""
        recommendations = []

        if pii_compliance_rate < 0.95:
            recommendations.append(
                "PII compliance rate is below 95%. Review PII detection and sanitization processes."
            )

        if data_quality_score < 0.8:
            recommendations.append(
                "Data quality score is below 80%. Consider improving error handling and data validation."
            )

        # Analyze error patterns
        if metrics:
            avg_processing_time = sum(m.avg_processing_time for m in metrics) / len(metrics)
            if avg_processing_time > 300:  # 5 minutes
                recommendations.append(
                    "Average processing time is high. Consider optimizing embedding pipeline performance."
                )

        # Check for operational issues
        recent_metrics = [m for m in metrics if m.timestamp > datetime.now(timezone.utc) - timedelta(hours=1)]
        if recent_metrics:
            recent_error_rate = sum(
                m.error_count / max(m.success_count + m.error_count, 1)
                for m in recent_metrics
            ) / len(recent_metrics)

            if recent_error_rate > 0.2:
                recommendations.append(
                    "Recent error rate is above 20%. Immediate attention required."
                )

        return recommendations

    async def get_monitoring_dashboard_data(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get data for monitoring dashboard.

        Args:
            tenant_id: Specific tenant (None for all)

        Returns:
            Dashboard data
        """
        try:
            # Get recent metrics
            recent_metrics = [
                m for m in self.metrics_buffer
                if tenant_id is None or m.tenant_id == tenant_id
            ]

            if not recent_metrics:
                return {"message": "No metrics available"}

            # Calculate summary statistics
            total_operations = sum(m.success_count + m.error_count for m in recent_metrics)
            total_success = sum(m.success_count for m in recent_metrics)
            total_errors = sum(m.error_count for m in recent_metrics)
            total_pii_violations = sum(m.pii_violations for m in recent_metrics)

            # Calculate trends
            trends = self._calculate_metric_trends(recent_metrics)

            dashboard_data = {
                "summary": {
                    "total_operations": total_operations,
                    "success_rate": total_success / total_operations if total_operations > 0 else 0,
                    "error_rate": total_errors / total_operations if total_operations > 0 else 0,
                    "pii_violations": total_pii_violations,
                    "avg_processing_time": sum(m.avg_processing_time for m in recent_metrics) / len(recent_metrics)
                },
                "trends": trends,
                "alerts": await self._get_active_alerts(tenant_id),
                "top_issues": self._get_top_issues(recent_metrics),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            return dashboard_data

        except Exception as e:
            self.logger.error(f"Failed to get dashboard data: {e}")
            return {"error": str(e)}

    def _calculate_metric_trends(self, metrics: List[VectorMetrics]) -> Dict[str, Any]:
        """Calculate trends from metrics."""
        if len(metrics) < 2:
            return {"message": "Insufficient data for trends"}

        # Sort by timestamp
        sorted_metrics = sorted(metrics, key=lambda m: m.timestamp)

        # Calculate simple trends (comparing first half vs second half)
        mid_point = len(sorted_metrics) // 2
        first_half = sorted_metrics[:mid_point]
        second_half = sorted_metrics[mid_point:]

        def avg_metric(half: List[VectorMetrics], attr: str) -> float:
            values = [getattr(m, attr) for m in half]
            return sum(values) / len(values) if values else 0

        trends = {
            "error_rate_trend": avg_metric(second_half, "error_rate") - avg_metric(first_half, "error_rate"),
            "processing_time_trend": avg_metric(second_half, "avg_processing_time") - avg_metric(first_half, "avg_processing_time"),
            "pii_violations_trend": avg_metric(second_half, "pii_violations") - avg_metric(first_half, "pii_violations")
        }

        return trends

    async def _get_active_alerts(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get currently active alerts."""
        # Placeholder implementation
        return []

    def _get_top_issues(self, metrics: List[VectorMetrics]) -> List[Dict[str, Any]]:
        """Get top issues from recent metrics."""
        issues = []

        if not metrics:
            return issues

        # Analyze error patterns
        total_errors = sum(m.error_count for m in metrics)
        if total_errors > 0:
            issues.append({
                "type": "high_error_rate",
                "severity": "medium",
                "description": f"Total errors: {total_errors}",
                "count": total_errors
            })

        # Analyze PII violations
        total_pii_violations = sum(m.pii_violations for m in metrics)
        if total_pii_violations > 0:
            issues.append({
                "type": "pii_violations",
                "severity": "high",
                "description": f"PII violations detected: {total_pii_violations}",
                "count": total_pii_violations
            })

        # Sort by severity and count
        issues.sort(key=lambda x: (x["severity"], x["count"]), reverse=True)

        return issues[:10]

    async def start_monitoring(self) -> None:
        """Start the monitoring service."""
        self.logger.info("Starting vector monitoring service")

        while True:
            try:
                # This would be called periodically to collect metrics and check alerts
                # For now, it's a placeholder for the monitoring loop
                await asyncio.sleep(self.metrics_collection_interval)

            except Exception as e:
                self.logger.error(f"Monitoring service error: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying

    async def stop_monitoring(self) -> None:
        """Stop the monitoring service."""
        self.logger.info("Stopping vector monitoring service")