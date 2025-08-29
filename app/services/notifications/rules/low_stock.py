from __future__ import annotations

from typing import cast

from app.services.notification_service import NotificationRule, NotificationRuleType
from app.services.notifications.schemas import NotificationAlert, AlertSource, map_severity
from app.services.notifications.utils import as_float, listv


class LowStockEvaluator:
    def evaluate(self, rule: NotificationRule, features: dict[str, object]) -> NotificationAlert | None:
        params = rule.parameters or {}
        threshold_units = as_float(params.get("threshold"), 10.0)
        critical_threshold = as_float(params.get("critical_threshold"), max(2.0, threshold_units / 5.0))

        low_items_any = listv(features, "low_stock_items")
        low_items: list[object] = cast(list[object], low_items_any)
        inv_level = as_float(features.get("inventory_level"), 1.0)

        metadata: dict[str, object] = {}
        if low_items:
            metadata["items"] = low_items
        if inv_level < 0.2:
            metadata["inventory_level"] = inv_level

        if low_items or inv_level < 0.2:
            sev = map_severity(cast(str | None, params.get("severity")), "warning")
            dict_items: list[dict[str, object]] = []
            for item in low_items:
                if isinstance(item, dict):
                    dict_items.append(cast(dict[str, object], item))
            if inv_level < 0.1 or any(as_float(it.get("qty"), threshold_units) <= critical_threshold for it in dict_items):
                sev = "error"
            return NotificationAlert(
                rule_type=NotificationRuleType.LOW_STOCK,
                severity=sev,
                title="Stock bajo detectado",
                message="Se detectaron productos con stock bajo o inventario general crítico.",
                metadata=metadata,
                score=1.0 - inv_level if inv_level <= 1 else 0.6,
                source=AlertSource.STATIC_RULE,
            )
        return None
