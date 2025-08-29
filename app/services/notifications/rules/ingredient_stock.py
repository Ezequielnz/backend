from __future__ import annotations

from typing import cast

from app.services.notification_service import NotificationRule, NotificationRuleType
from app.services.notifications.schemas import NotificationAlert, AlertSource, map_severity
from app.services.notifications.utils import as_float, listv


class IngredientStockEvaluator:
    def evaluate(self, rule: NotificationRule, features: dict[str, object]) -> NotificationAlert | None:
        params = rule.parameters or {}
        threshold_pct = as_float(params.get("threshold"), 20.0)
        crit_pct = as_float(params.get("critical_threshold"), 5.0)

        ingred_any = listv(features, "ingredient_low_list")
        ingred_list: list[object] = cast(list[object], ingred_any)
        if ingred_list:
            sev = map_severity(cast(str | None, params.get("severity")), "warning")
            dict_ingr: list[dict[str, object]] = []
            for item in ingred_list:
                if isinstance(item, dict):
                    dict_ingr.append(cast(dict[str, object], item))
            if any(as_float(it.get("pct"), 100.0) <= crit_pct for it in dict_ingr):
                sev = "error"
            return NotificationAlert(
                rule_type=NotificationRuleType.INGREDIENT_STOCK,
                severity=sev,
                title="Ingredientes con stock bajo",
                message="Hay ingredientes por debajo de los umbrales definidos.",
                metadata={"ingredients": ingred_list, "threshold_pct": threshold_pct},
                score=0.8,
                source=AlertSource.STATIC_RULE,
            )
        return None
