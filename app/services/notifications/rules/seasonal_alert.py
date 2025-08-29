from __future__ import annotations

from typing import cast
from datetime import datetime

from app.services.notification_service import NotificationRule, NotificationRuleType
from app.services.notifications.schemas import NotificationAlert, AlertSource, map_severity


class SeasonalAlertEvaluator:
    def evaluate(self, rule: NotificationRule, features: dict[str, object]) -> NotificationAlert | None:
        params = rule.parameters or {}
        peak_seasons = cast(list[str], params.get("peak_seasons", []))
        now_month = datetime.now().strftime("%B").lower()

        if any(m for m in peak_seasons if now_month.startswith(m[:3].lower())):
            return NotificationAlert(
                rule_type=NotificationRuleType.SEASONAL_ALERT,
                severity=map_severity("info"),
                title="Temporada alta próxima",
                message="Prepara inventario y promociones para la temporada alta.",
                metadata={"peak_seasons": peak_seasons},
                score=0.5,
                source=AlertSource.STATIC_RULE,
            )
        return None
