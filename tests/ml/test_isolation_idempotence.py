import types
import pandas as pd
import numpy as np
import pytest
from typing import Any, cast

from app.services.ml.pipeline import train_and_predict_sales


class FakeQuery:
    def __init__(self, table_name: str, store: dict[str, list[dict[str, Any]]]):
        self.table_name = table_name
        self._store = store
        self._payload: list[dict[str, Any]] | dict[str, Any] | None = None
        self._on_conflict: str | None = None
        self._select = None
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None
        self._order: tuple[str, bool] | None = None

    def select(self, fields: str) -> "FakeQuery":
        self._select = fields
        return self

    def eq(self, field: str, value: Any) -> "FakeQuery":
        self._filters.append(("eq", field, value))
        return self

    def limit(self, n: int) -> "FakeQuery":
        self._limit = n
        return self

    def order(self, field: str, desc: bool = False) -> "FakeQuery":
        self._order = (field, desc)
        return self

    def upsert(self, payload: Any, on_conflict: str | None = None) -> "FakeQuery":
        self._payload = payload
        self._on_conflict = on_conflict
        return self

    def insert(self, payload: Any) -> "FakeQuery":
        self._payload = payload
        return self

    def execute(self) -> Any:
        if self.table_name == "ml_predictions" and self._payload is not None:
            rows = cast(list[dict[str, Any]], self._payload)
            keys = [k.strip() for k in (self._on_conflict or "").split(",") if k.strip()]
            existing = self._store.setdefault("ml_predictions", [])
            if keys:
                for r in rows:
                    def _match(e: dict[str, Any]) -> bool:
                        return all(str(e.get(k)) == str(r.get(k)) for k in keys)
                    idx = next((i for i, e in enumerate(existing) if _match(e)), None)
                    if idx is None:
                        existing.append(r)
                    else:
                        existing[idx] = r
            else:
                existing.extend(rows)
            return types.SimpleNamespace(data=rows)
        if self.table_name == "ml_models" and self._payload is not None:
            payload = cast(dict[str, Any], self._payload)
            row = {
                "id": payload.get("id", "model_1"),
                "tenant_id": payload.get("tenant_id", "t1"),
                "model_type": payload.get("model_type", "sales_forecasting"),
                "model_version": payload.get("model_version", "1.0"),
                "accuracy": payload.get("accuracy"),
                "created_at": "2024-01-01T00:00:00Z",
            }
            keys = [k.strip() for k in (self._on_conflict or "").split(",") if k.strip()]
            existing = self._store.setdefault("ml_models", [])
            if keys:
                def _match(e: dict[str, Any]) -> bool:
                    return all(str(e.get(k)) == str(row.get(k)) for k in keys)
                idx = next((i for i, e in enumerate(existing) if _match(e)), None)
                if idx is None:
                    existing.append(row)
                else:
                    existing[idx] = row
            else:
                existing.append(row)
            return types.SimpleNamespace(data=[row])
        return types.SimpleNamespace(data=[])


class FakeSupabase:
    def __init__(self):
        self.store: dict[str, list[dict[str, Any]]] = {}

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(name, self.store)


# Reuse base fixture by importing from existing test module
from test_ml_candidates_and_drift import timeseries_60d  # noqa: E402


def _patch_supabase(monkeypatch: pytest.MonkeyPatch, fake: FakeSupabase) -> None:
    from app.services.ml import pipeline as pipe_mod
    from app.services.ml import model_version_manager as mvm_mod
    monkeypatch.setattr(pipe_mod, "get_supabase_service_client", lambda: fake)
    monkeypatch.setattr(mvm_mod, "get_supabase_service_client", lambda: fake)


def test_isolation_multi_tenant_upserts(monkeypatch: pytest.MonkeyPatch, timeseries_60d: pd.DataFrame):
    fake = FakeSupabase()
    _patch_supabase(monkeypatch, fake)
    from app.services.ml import feature_engineer as fe_mod
    monkeypatch.setattr(fe_mod.FeatureEngineer, "sales_timeseries_daily", lambda self, tenant_id, days=365: timeseries_60d)

    for tenant in ("tenant_a", "tenant_b"):
        _ = train_and_predict_sales(
            tenant,
            horizon_days=7,
            history_days=60,
            include_anomaly=False,
            model_candidates="naive,prophet",
            cv_folds=2,
        )

    rows = fake.store.get("ml_predictions", [])
    assert rows, "No predictions inserted"
    # Separate by tenant
    a_rows = [r for r in rows if r.get("tenant_id") == "tenant_a"]
    b_rows = [r for r in rows if r.get("tenant_id") == "tenant_b"]
    assert len(a_rows) >= 7 and len(b_rows) >= 7
    # Disjoint by (tenant, date, type)
    keys_a = {(r.get("tenant_id"), r.get("prediction_date"), r.get("prediction_type")) for r in a_rows}
    keys_b = {(r.get("tenant_id"), r.get("prediction_date"), r.get("prediction_type")) for r in b_rows}
    assert keys_a.isdisjoint(keys_b)


def test_idempotence_upserts_and_model(monkeypatch: pytest.MonkeyPatch, timeseries_60d: pd.DataFrame):
    fake = FakeSupabase()
    _patch_supabase(monkeypatch, fake)
    from app.services.ml import feature_engineer as fe_mod
    monkeypatch.setattr(fe_mod.FeatureEngineer, "sales_timeseries_daily", lambda self, tenant_id, days=365: timeseries_60d)

    # Run twice same tenant/horizon/day
    for _ in range(2):
        _ = train_and_predict_sales(
            "tenant_x",
            horizon_days=7,
            history_days=60,
            include_anomaly=False,
            model_candidates="naive,prophet",
            cv_folds=2,
        )

    # Predictions should be unique by (tenant_id, prediction_date, prediction_type)
    rows = fake.store.get("ml_predictions", [])
    keyset = {(r.get("tenant_id"), r.get("prediction_date"), r.get("prediction_type")) for r in rows}
    assert len(keyset) == 7

    # Models should upsert per (tenant_id, model_type, model_version)
    models = fake.store.get("ml_models", [])
    keyset_models = {(m.get("tenant_id"), m.get("model_type"), m.get("model_version")) for m in models}
    assert len(keyset_models) == 1
