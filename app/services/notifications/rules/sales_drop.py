from __future__ import annotations

from typing import cast

from app.services.notification_service import NotificationRule, NotificationRuleType
from app.services.notifications.schemas import NotificationAlert, AlertSource, map_severity
from app.services.notifications.utils import as_float


class SalesDropEvaluator:
    def evaluate(self, rule: NotificationRule, features: dict[str, object]) -> NotificationAlert | None:
        params = rule.parameters or {}
        threshold = as_float(params.get("threshold"), 20.0)  # percent
        # Try sales_growth (e.g., -0.15 means -15%) or sales_trend
        growth = as_float(features.get("sales_growth"), as_float(features.get("sales_trend"), 0.0)) * 100.0

        if growth < -threshold:
            pct = round(growth, 1)
            return NotificationAlert(
                rule_type=NotificationRuleType.SALES_DROP,
                severity=map_severity(cast(str | None, params.get("severity")), "warning"),
                title="Caída de ventas detectada",
                message=f"Las ventas han caído {abs(pct)}% respecto al período anterior.",
                metadata={"sales_growth_pct": pct, "threshold_pct": threshold},
                score=min(1.0, abs(growth) / max(1.0, threshold)),
                source=AlertSource.STATIC_RULE,
            )
        return None
