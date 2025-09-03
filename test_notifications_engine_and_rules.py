from __future__ import annotations

import math
from typing import Any, cast

from app.services.notification_service import NotificationRule, NotificationRuleType
from app.services.notifications.rules.registry import evaluate_rule
from app.services.notification_rule_engine import NotificationRuleEngine
from app.services.notifications.schemas import AlertSource


# -------------------- Helpers --------------------

def make_rule(rt: NotificationRuleType, params: dict[str, object] | None = None, active: bool = True) -> NotificationRule:
    return NotificationRule(
        rule_type=rt,
        condition_config={},
        parameters=params or {},
        is_active=active,
    )


# -------------------- Unit tests: Evaluators via registry --------------------

def test_sales_drop_evaluator_triggers():
    rule = make_rule(NotificationRuleType.SALES_DROP, {"threshold": 20})
    features: dict[str, object] = {"sales_growth": -0.25}  # -25%
    alert = evaluate_rule(rule, features)
    assert alert is not None
    assert alert.rule_type == NotificationRuleType.SALES_DROP
    assert alert.severity == "warning"
    assert cast(dict[str, object], alert.metadata).get("sales_growth_pct") == -25.0
    assert alert.source == AlertSource.STATIC_RULE


def test_high_expenses_evaluator_threshold_and_score():
    rule = make_rule(NotificationRuleType.HIGH_EXPENSES, {"threshold": 120})
    features: dict[str, object] = {"expense_ratio": 130}
    alert = evaluate_rule(rule, features)
    assert alert is not None
    assert alert.rule_type == NotificationRuleType.HIGH_EXPENSES
    assert alert.severity == "warning"
    # Score per formula: min(1.0, (expense_ratio - threshold + 1)/threshold)
    expected_score = min(1.0, (130 - 120 + 1.0) / 120.0)
    assert math.isclose(alert.score, expected_score, rel_tol=1e-6)


def test_low_stock_evaluator_critical_by_item_qty():
    rule = make_rule(NotificationRuleType.LOW_STOCK)
    features: dict[str, object] = {
        "inventory_level": 0.5,
        "low_stock_items": [
            {"name": "A", "qty": 1.0},  # <= critical_threshold (default 2)
            {"name": "B", "qty": 5.0},
        ],
    }
    alert = evaluate_rule(rule, features)
    assert alert is not None
    assert alert.rule_type == NotificationRuleType.LOW_STOCK
    assert alert.severity == "error"  # critical due to qty <= critical_threshold
    assert alert.source == AlertSource.STATIC_RULE


def test_low_stock_evaluator_inventory_low_warning():
    rule = make_rule(NotificationRuleType.LOW_STOCK)
    features: dict[str, object] = {
        "inventory_level": 0.18,
        "low_stock_items": [],
    }
    alert = evaluate_rule(rule, features)
    assert alert is not None
    assert alert.severity == "warning"
    assert cast(dict[str, object], alert.metadata).get("inventory_level") == 0.18
    # score ~ 1 - inv_level when <=1
    assert math.isclose(alert.score, 0.82, rel_tol=1e-6)


def test_ingredient_stock_evaluator_critical_by_pct():
    rule = make_rule(NotificationRuleType.INGREDIENT_STOCK, {"critical_threshold": 5.0})
    features: dict[str, object] = {
        "ingredient_low_list": [
            {"name": "Harina", "pct": 4.0},  # <= critical_threshold
            {"name": "Azucar", "pct": 12.0},
        ]
    }
    alert = evaluate_rule(rule, features)
    assert alert is not None
    assert alert.rule_type == NotificationRuleType.INGREDIENT_STOCK
    assert alert.severity == "error"


def test_no_purchases_evaluator_triggers():
    rule = make_rule(NotificationRuleType.NO_PURCHASES, {"threshold": 5})
    features: dict[str, object] = {"days_without_purchases": 7}
    alert = evaluate_rule(rule, features)
    assert alert is not None
    assert alert.rule_type == NotificationRuleType.NO_PURCHASES
    assert alert.severity == "warning"


def test_seasonal_alert_evaluator_current_month_prefix():
    import datetime as _dt

    now_month = _dt.datetime.now().strftime("%B").lower()
    # pass first 3 chars to match logic
    rule = make_rule(NotificationRuleType.SEASONAL_ALERT, {"peak_seasons": [now_month[:3]]})
    features: dict[str, object] = {}
    alert = evaluate_rule(rule, features)
    assert alert is not None
    assert alert.rule_type == NotificationRuleType.SEASONAL_ALERT
    assert alert.severity == "info"


# -------------------- Integration: Engine evaluate + dedupe --------------------

def test_engine_evaluate_with_dedupe_static_vs_ml():
    engine = NotificationRuleEngine()

    # fake effective rules: one SALES_DROP with severe custom severity via parameters
    rules = [
        make_rule(NotificationRuleType.SALES_DROP, {"threshold": 10, "severity": "error"}),
    ]

    async def fake_get_rules(_tenant_id: str):
        return rules

    # monkeypatch the async getter
    cast(Any, engine.config_service).get_effective_rules = fake_get_rules

    tenant = "test-tenant-1"
    features: dict[str, object] = {"sales_growth": -0.30}  # -30% => triggers static with severity error
    predictions: list[dict[str, object]] = [
        {"prediction_type": "sales_drop_risk", "confidence": 0.7},
    ]

    alerts = engine.evaluate(tenant, features=features, predictions=predictions)
    # deduped should keep one SALES_DROP with higher severity and merged metadata
    assert len(alerts) == 1
    a = alerts[0]
    assert a.rule_type == NotificationRuleType.SALES_DROP
    assert a.severity == "error"  # prefer static error over ml warning
    # metadata merged: has sales_growth_pct and prediction
    assert "sales_growth_pct" in a.metadata
    assert "prediction" in a.metadata
    # source combined because we merged static + ml
    assert a.source == AlertSource.COMBINED
