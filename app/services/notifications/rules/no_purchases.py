from __future__ import annotations

from typing import cast

from app.services.notification_service import NotificationRule, NotificationRuleType
from app.services.notifications.schemas import NotificationAlert, AlertSource, map_severity
from app.services.notifications.utils import as_float


class NoPurchasesEvaluator:
    def evaluate(self, rule: NotificationRule, features: dict[str, object]) -> NotificationAlert | None:
        params = rule.parameters or {}
        days = as_float(params.get("threshold"), 5.0)
        days_without = as_float(features.get("days_without_purchases"), 0.0)
        if days_without > days:
            return NotificationAlert(
                rule_type=NotificationRuleType.NO_PURCHASES,
                severity=map_severity(cast(str | None, params.get("severity")), "warning"),
                title="Sin compras recientes",
                message=f"No se registran compras desde hace {int(days_without)} días.",
                metadata={"days_without_purchases": days_without, "threshold_days": days},
                score=min(1.0, (days_without - days) / max(1.0, days)),
                source=AlertSource.STATIC_RULE,
            )
        return None
