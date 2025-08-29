from __future__ import annotations

from typing import Protocol

from app.services.notification_service import NotificationRule
from app.services.notifications.schemas import NotificationAlert


class RuleEvaluator(Protocol):
    def evaluate(self, rule: NotificationRule, features: dict[str, object]) -> NotificationAlert | None: ...
