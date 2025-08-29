from __future__ import annotations

from typing import Callable

from app.services.notification_service import NotificationRule, NotificationRuleType
from app.services.notifications.schemas import NotificationAlert

from .sales_drop import SalesDropEvaluator
from .low_stock import LowStockEvaluator
from .ingredient_stock import IngredientStockEvaluator
from .no_purchases import NoPurchasesEvaluator
from .seasonal_alert import SeasonalAlertEvaluator
from .high_expenses import HighExpensesEvaluator


# Mapping from rule type to evaluator instance
EVALUATORS: dict[NotificationRuleType, Callable[[NotificationRule, dict[str, object]], NotificationAlert | None]] = {
    NotificationRuleType.SALES_DROP: SalesDropEvaluator().evaluate,
    NotificationRuleType.LOW_STOCK: LowStockEvaluator().evaluate,
    NotificationRuleType.INGREDIENT_STOCK: IngredientStockEvaluator().evaluate,
    NotificationRuleType.NO_PURCHASES: NoPurchasesEvaluator().evaluate,
    NotificationRuleType.SEASONAL_ALERT: SeasonalAlertEvaluator().evaluate,
    NotificationRuleType.HIGH_EXPENSES: HighExpensesEvaluator().evaluate,
}


def get_evaluator(rule_type: NotificationRuleType) -> Callable[[NotificationRule, dict[str, object]], NotificationAlert | None]:
    return EVALUATORS[rule_type]
def evaluate_rule(rule: NotificationRule, features: dict[str, object]) -> NotificationAlert | None:
    fn = EVALUATORS.get(rule.rule_type)
    if not fn:
        return None
    return fn(rule, features)