from __future__ import annotations

import logging
from typing import cast, Callable

from app.db.supabase_client import get_supabase_service_client, TableQueryProto
from app.workers.notification_worker import send_notification


def _as_float(x: object, default: float = 0.0) -> float:
    """Safe conversion to float."""
    try:
        if x is None:
            return default
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip()
        if s == "" or s.lower() in ("nan", "none"):
            return default
        return float(s)
    except Exception:
        return default

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """
    Engine for generating ML-based recommendations for stock and sales reviews.
    Consumes predictions from ml_predictions and triggers notifications.
    """

    def __init__(self) -> None:
        self.client = get_supabase_service_client()

    def _table(self, name: str) -> TableQueryProto:
        table_fn: Callable[[str], object] = cast(Callable[[str], object], getattr(self.client, "table"))
        return cast(TableQueryProto, table_fn(name))

    def _send_notification(self, tenant_id: str, notification_type: str, data: dict[str, object]) -> None:
        """Send notification via Celery task."""
        try:
            cast(object, send_notification).delay(tenant_id, notification_type, data)  # type: ignore[attr-defined]
        except Exception as e:
            logger.error("Failed to send notification: %s", e)

    def check_stock_recommendations(self, tenant_id: str, buffer_pct: float = 0.1) -> int:
        """
        Check stock levels against forecasted sales and recommend purchases if needed.
        Returns number of recommendations sent.
        """
        try:
            # Get latest forecasts (next 7 days)
            forecasts_resp = self._table("ml_predictions").select(
                "prediction_date, predicted_values"
            ).eq("tenant_id", tenant_id).eq("prediction_type", "sales_forecast").gte(
                "prediction_date", "now()::date"
            ).lte("prediction_date", "now()::date + interval '7 days'").execute()
            forecasts = cast(list[dict[str, object]], forecasts_resp.data or [])

            if not forecasts:
                logger.info("No forecasts available for stock recommendations tenant=%s", tenant_id)
                return 0

            # Sum forecasted sales over next 7 days
            total_forecast = sum(
                _as_float(cast(dict[str, object], f["predicted_values"]).get("yhat", 0.0))
                for f in forecasts
            )

            # Get current stock levels
            stock_resp = self._table("productos").select(
                "id, nombre, stock_actual, precio_compra"
            ).eq("negocio_id", tenant_id).gte("stock_actual", 1).execute()
            products = cast(list[dict[str, object]], stock_resp.data or [])

            recommendations_sent = 0
            for product in products:
                stock = cast(float, product.get("stock_actual", 0.0))
                if stock <= total_forecast * (1 + buffer_pct):
                    # Recommend purchase
                    msg = {
                        "title": "Recomendación de compra de stock",
                        "message": f"El producto '{product.get('nombre')}' tiene stock bajo ({stock}) comparado con la previsión de ventas ({total_forecast:.1f}). Considera reponer.",
                        "severity": "info",
                        "metadata": {
                            "product_id": product.get("id"),
                            "current_stock": stock,
                            "forecasted_sales": total_forecast,
                            "buffer_pct": buffer_pct,
                        },
                        "score": 0.8,  # High confidence for stock alerts
                        "source": "ml_recommendation",
                    }
                    self._send_notification(tenant_id, "stock_recommendation", msg)
                    recommendations_sent += 1

            logger.info("Stock recommendations sent: %d for tenant=%s", recommendations_sent, tenant_id)
            return recommendations_sent

        except Exception as e:
            logger.error("Error in stock recommendations for tenant=%s: %s", tenant_id, e)
            return 0

    def check_sales_review_recommendations(self, tenant_id: str, drift_threshold: float = 0.2) -> int:
        """
        Check for sales anomalies or drift and recommend reviews.
        Returns number of recommendations sent.
        """
        try:
            # Get recent anomalies (last 30 days)
            anomalies_resp = self._table("ml_predictions").select(
                "prediction_date, predicted_values"
            ).eq("tenant_id", tenant_id).eq("prediction_type", "sales_anomaly").gte(
                "prediction_date", "now()::date - interval '30 days'"
            ).execute()
            anomalies = cast(list[dict[str, object]], anomalies_resp.data or [])

            if not anomalies:
                logger.info("No anomalies for sales review recommendations tenant=%s", tenant_id)
                return 0

            # Count anomalies and check for patterns
            anomaly_count = len(anomalies)
            if anomaly_count >= 3:  # Threshold for recommendation
                msg = {
                    "title": "Recomendación de revisión de ventas",
                    "message": f"Se detectaron {anomaly_count} anomalías en ventas en los últimos 30 días. Considera revisar estrategias de marketing o precios.",
                    "severity": "warning",
                    "metadata": {
                        "anomaly_count": anomaly_count,
                        "period_days": 30,
                        "drift_threshold": drift_threshold,
                    },
                    "score": 0.7,
                    "source": "ml_recommendation",
                }
                self._send_notification(tenant_id, "sales_review_recommendation", msg)
                logger.info("Sales review recommendation sent for tenant=%s", tenant_id)
                return 1

            return 0

        except Exception as e:
            logger.error("Error in sales review recommendations for tenant=%s: %s", tenant_id, e)
            return 0


# Convenience functions
def check_stock_recommendations(tenant_id: str, buffer_pct: float = 0.1) -> int:
    engine = RecommendationEngine()
    return engine.check_stock_recommendations(tenant_id, buffer_pct)


def check_sales_review_recommendations(tenant_id: str, drift_threshold: float = 0.2) -> int:
    engine = RecommendationEngine()
    return engine.check_sales_review_recommendations(tenant_id, drift_threshold)