"""
Hybrid Notification Rule Engine
- Loads tenant-effective rules (templates + overrides)
- Evaluates static rules against business features
- Combines with ML suggestions
- Deduplicates and produces final alerts
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import cast, TypeVar, Callable, Protocol
from collections.abc import Awaitable
import logging
from supabase.client import Client

from app.services.notification_service import (
    NotificationConfigService,
    NotificationRule,
    NotificationRuleType,
)
from app.db.supabase_client import get_supabase_service_client
from app.core.cache_manager import cache_manager, CacheManager
from app.services.notifications.schemas import NotificationAlert, AlertSource
from app.services.notifications.rules.registry import evaluate_rule as _evaluate_static_rule
from app.services.notifications.utils import sev_rank

logger = logging.getLogger(__name__)


T = TypeVar("T")


class NotificationRuleEngine:
    """
    Core engine that evaluates rules for a tenant and merges with ML suggestions.
    """

    def __init__(self) -> None:
        # Use service client so Celery can bypass RLS safely (server-side tasks)
        super().__init__()
        self.supabase: Client = get_supabase_service_client()
        self.config_service: NotificationConfigService = NotificationConfigService()
        self.cache: CacheManager = cache_manager
        self.logger: logging.Logger = logging.getLogger(__name__)
    
    def _table(self, name: str) -> _SyncTable:
        """Return a sync table builder typed as _SyncTable, avoiding unknown member type warnings."""
        table_fn = cast(Callable[[str], object], getattr(self.supabase, "table"))
        return cast(_SyncTable, table_fn(name))
    
    def _run_coro(self, coro: Awaitable[T]) -> T:
        """Run an async coroutine in a safe way from sync context (Celery)."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        if loop.is_running():
            # Fallback: create a new loop to run sync
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
        return loop.run_until_complete(coro)

    # --------------------------- Feature/Prediction IO ---------------------------
    def _unify_feature_row(self, row: dict[str, object]) -> dict[str, object]:
        """Unify different possible shapes of ml_features rows into a flat feature dict."""
        # Preferred schema: features JSONB
        if "features" in row and isinstance(row["features"], dict):
            return cast(dict[str, object], row["features"])  # type: ignore
        # Legacy fields used by older worker simulation
        keys = [
            "sales_trend",
            "inventory_level",
            "customer_activity",
            "days_without_purchases",
            "low_stock_items",
            "ingredient_low_list",
            "expense_ratio",
            "sales_growth",
        ]
        features: dict[str, object] = {}
        for k in keys:
            if k in row:
                features[k] = row[k]
        return features

    def _unify_prediction_row(self, row: dict[str, object]) -> dict[str, object]:
        """Unify different possible shapes of ml_predictions rows into a consistent dict."""
        # Preferred schema
        if "predicted_values" in row and isinstance(row["predicted_values"], dict):
            base: dict[str, object] = cast(dict[str, object], row["predicted_values"])  # type: ignore
            base["prediction_type"] = row.get("prediction_type") or row.get("type")
            base["confidence"] = row.get("confidence_score")
            return base
        # Legacy fields
        return {
            "prediction_type": row.get("type"),
            "value": row.get("value"),
            "confidence": row.get("confidence"),
        }

    def _cache_key(self, tenant_id: str, key: str) -> str:
        return f"{tenant_id}:{key}"

    def _as_float(self, v: object | None, default: float) -> float:
        """Best-effort conversion of arbitrary objects to float with a safe default.
        Avoids typing issues with direct float() on objects while keeping runtime behavior robust.
        """
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v)
            except Exception:
                return default
        return default

    def get_latest_features(self, tenant_id: str) -> dict[str, object]:
        """Fetch latest ML features for tenant with caching. Compatible with tenant_id/business_id and created_at/updated_at columns."""
        ck = self._cache_key(tenant_id, "latest_features")
        cached = self.cache.get("ml_features", ck)
        if cached is not None:
            return cast(dict[str, object], cached)

        features: dict[str, object] = {}
        # Try multiple query strategies for compatibility with legacy schemas
        query_variants = [
            ("tenant_id", "created_at"),
            ("tenant_id", "updated_at"),
            ("business_id", "created_at"),
            ("business_id", "updated_at"),
        ]
        for id_col, order_col in query_variants:
            try:
                table_features = self._table("ml_features")
                resp_obj = (
                    table_features
                    .select("*")
                    .eq(id_col, tenant_id)
                    .order(order_col, desc=True)
                    .limit(1)
                    .execute()
                )
                data = cast(list[dict[str, object]], getattr(resp_obj, "data", []) or [])
                row = data[0] if data else None
                if row:
                    features = self._unify_feature_row(row)
                    break
            except Exception:
                continue

        if not features:
            self.logger.info("ml_features not found for tenant/business; returning empty features")

        self.cache.set("ml_features", ck, features, ttl=3600)
        return features

    def get_recent_predictions(self, tenant_id: str, limit: int = 5) -> list[dict[str, object]]:
        """Fetch recent ML predictions for tenant with caching. Supports tenant_id and business_id schemas."""
        ck = self._cache_key(tenant_id, f"predictions_{limit}")
        cached = self.cache.get("ml_predictions", ck)
        if cached is not None:
            return cast(list[dict[str, object]], cached)

        preds: list[dict[str, object]] = []
        for id_col in ("tenant_id", "business_id"):
            try:
                table_preds = self._table("ml_predictions")
                resp_obj = (
                    table_preds
                    .select("*")
                    .eq(id_col, tenant_id)
                    .order("created_at", desc=True)
                    .limit(limit)
                    .execute()
                )
                rows = cast(list[dict[str, object]], getattr(resp_obj, "data", []) or [])
                if rows:
                    preds = [self._unify_prediction_row(r) for r in rows]
                    break
            except Exception:
                continue

        if not preds:
            self.logger.info("ml_predictions not found for tenant/business; returning empty list")

        self.cache.set("ml_predictions", ck, preds, ttl=1800)
        return preds

    # --------------------------- Evaluation ---------------------------
    def _rule_type_value(self, rt: object) -> str:
        """Return a stable string value for a rule_type that may be an enum or arbitrary object."""
        try:
            # Avoid top-level import cycle by importing here
            from app.services.notification_service import NotificationRuleType as _RT  # type: ignore
            if isinstance(rt, _RT):
                return rt.value
        except Exception:
            pass
        v = getattr(rt, "value", None)
        return str(v if v is not None else rt)

    def evaluate(self, tenant_id: str, features: dict[str, object] | None = None, predictions: list[dict[str, object]] | None = None) -> list[NotificationAlert]:
        """
        Evaluate static rules and combine with ML suggestions, returning final deduped alerts.
        """
        # Load effective rules (service method is async)
        get_rules = cast(Callable[[str], Awaitable[list[NotificationRule]]], self.config_service.get_effective_rules)
        rules: list[NotificationRule] = self._run_coro(get_rules(tenant_id))

        if not rules:
            return []

        feat = features or self.get_latest_features(tenant_id)
        preds = predictions or self.get_recent_predictions(tenant_id)

        static_alerts: list[NotificationAlert] = []
        for rule in rules:
            if not rule.is_active:
                continue
            try:
                ra = self._evaluate_rule(rule, feat)
                if ra:
                    static_alerts.append(ra)
            except Exception as e:
                self.logger.error(f"Error evaluating rule {rule.rule_type} for {tenant_id}: {e}")

        combined = self._combine_with_ml(static_alerts, preds)
        deduped = self._dedupe_alerts(combined)
        return deduped

    def _evaluate_rule(self, rule: NotificationRule, features: dict[str, object]) -> NotificationAlert | None:
        return _evaluate_static_rule(rule, features)

    def _combine_with_ml(self, static_alerts: list[NotificationAlert], predictions: list[dict[str, object]]) -> list[NotificationAlert]:
        """Turn ML predictions into alerts and combine with static alerts."""
        ml_alerts: list[NotificationAlert] = []
        for p in predictions:
            ptype = str(p.get("prediction_type") or "").lower()
            conf = self._as_float(p.get("confidence"), 0.0)
            # Simple mapping from prediction types to rule types
            mapped: NotificationRuleType | None = None
            title = ""
            message = ""
            severity = "warning"
            if "sales" in ptype and "drop" in ptype:
                mapped = NotificationRuleType.SALES_DROP
                title = "ML: Riesgo de caída de ventas"
                message = "El modelo predice una posible caída de ventas. Revisa promociones y stock."
            elif "stock" in ptype or "inventory" in ptype:
                mapped = NotificationRuleType.LOW_STOCK
                title = "ML: Riesgo de quiebre de stock"
                message = "El modelo anticipa problemas de stock en próximos días."
            elif "expense" in ptype or "cost" in ptype:
                mapped = NotificationRuleType.HIGH_EXPENSES
                title = "ML: Riesgo de gastos altos"
                message = "El modelo detecta tendencia de gastos superiores al presupuesto."

            if mapped is not None:
                ml_alerts.append(
                    NotificationAlert(
                        rule_type=mapped,
                        severity=severity,
                        title=title,
                        message=message,
                        metadata={"prediction": p},
                        score=min(1.0, max(0.1, conf)),
                        source=AlertSource.ML,
                    )
                )

        return static_alerts + ml_alerts

    def _dedupe_alerts(self, alerts: list[NotificationAlert]) -> list[NotificationAlert]:
        """Deduplicate alerts by rule_type, prefer higher severity/score, merge metadata."""
        best: dict[str, NotificationAlert] = {}
        for a in alerts:
            key = self._rule_type_value(cast(object, a.rule_type))
            if key not in best:
                best[key] = a
                continue
            cur = best[key]
            # Prefer higher severity, then score
            if (sev_rank(a.severity), a.score) > (sev_rank(cur.severity), cur.score):
                # Merge metadata
                merged = {**cur.metadata, **a.metadata}
                a.metadata = merged
                a.source = AlertSource.COMBINED if a.source != cur.source else a.source
                best[key] = a
            else:
                cur.metadata = {**a.metadata, **cur.metadata}
                cur.source = AlertSource.COMBINED if a.source != cur.source else cur.source
                best[key] = cur
        return list(best.values())

    # --------------------------- Persistence ---------------------------
    def persist_alerts(self, tenant_id: str, alerts: list[NotificationAlert]) -> int:
        """
        Write alerts into notifications table, with lightweight cache-based dedupe to avoid spam.
        Returns number of notifications inserted.
        """
        inserted = 0
        for a in alerts:
            dedupe_key = self._cache_key(tenant_id, f"notif:{self._rule_type_value(cast(object, a.rule_type))}:{a.severity}")
            if self.cache.get("notifications", dedupe_key):
                # Recently sent similar notification
                continue

            row = a.to_db_row(tenant_id)
            try:
                table_notif = self._table("notifications")
                _resp = table_notif.insert(row).execute()  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
                _ = _resp
                inserted += 1
                # Avoid re-sending same alert for 1 hour
                self.cache.set("notifications", dedupe_key, True, ttl=3600)
            except Exception as e:
                # Fallback to legacy schema: business_id/type/data/status
                try:
                    legacy_row: dict[str, object] = {
                        "business_id": tenant_id,
                        "type": self._rule_type_value(cast(object, a.rule_type)),
                        "data": {
                            "title": a.title,
                            "message": a.message,
                            "metadata": a.metadata,
                            "severity": a.severity,
                            "score": a.score,
                            "source": a.source.value,
                        },
                        "status": "sent",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    table_notif2 = self._table("notifications")
                    _resp2 = table_notif2.insert(legacy_row).execute()  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
                    _ = _resp2
                    inserted += 1
                    self.cache.set("notifications", dedupe_key, True, ttl=3600)
                except Exception as e2:
                    self.logger.error(
                        f"Failed to insert notification for {tenant_id}: {e}; legacy insert also failed: {e2}"
                    )
        return inserted

    # Convenience: evaluate and persist in one call
    def evaluate_and_persist(self, tenant_id: str, features: dict[str, object] | None = None, predictions: list[dict[str, object]] | None = None) -> dict[str, object]:
        alerts = self.evaluate(tenant_id, features, predictions)
        count = self.persist_alerts(tenant_id, alerts)
        return {
            "tenant_id": tenant_id,
            "alerts": len(alerts),
            "persisted": count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

# Minimal protocol to type Supabase sync table builders we use
class _SyncTable(Protocol):
    def select(self, columns: str) -> "_SyncTable": ...
    def eq(self, column: str, value: object) -> "_SyncTable": ...
    def order(self, column: str, desc: bool = False) -> "_SyncTable": ...
    def limit(self, n: int) -> "_SyncTable": ...
    def insert(self, data: dict[str, object] | list[dict[str, object]], *, count: object | None = None, returning: object | None = None, upsert: bool = False) -> "_SyncTable": ...
    def execute(self) -> object: ...
