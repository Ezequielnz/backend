from __future__ import annotations

from typing import cast
from app.services.notification_service import NotificationRule, NotificationRuleType
from app.services.notifications.schemas import NotificationAlert, AlertSource, map_severity
from app.services.notifications.utils import as_float


class HighExpensesEvaluator:
    def evaluate(self, rule: NotificationRule, features: dict[str, object]) -> NotificationAlert | None:
        params = rule.parameters or {}
        threshold_pct = as_float(params.get("threshold"), 120.0)
        expense_ratio = as_float(features.get("expense_ratio"), 100.0)

        if expense_ratio >= threshold_pct:
            return NotificationAlert(
                rule_type=NotificationRuleType.HIGH_EXPENSES,
                severity=map_severity(cast(str | None, params.get("severity")), "warning"),
                title="Gastos por encima del presupuesto",
                message=f"Los gastos alcanzaron {expense_ratio:.0f}% del presupuesto.",
                metadata={"expense_ratio_pct": expense_ratio, "threshold_pct": threshold_pct},
                score=min(1.0, (expense_ratio - threshold_pct + 1.0) / max(1.0, threshold_pct)),
                source=AlertSource.STATIC_RULE,
            )
        return None
