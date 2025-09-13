import math
import types
import pandas as pd
import numpy as np
import pytest
import importlib.util as _importlib_util

from typing import Any, Callable, cast

# Under test
from app.services.ml.ml_engine import BusinessMLEngine
from app.services.ml.pipeline import train_and_predict_sales
from app.config.ml_settings import ml_settings


class FakeQuery:
    def __init__(self, table_name: str, store: dict[str, list[dict[str, Any]]]):
        self.table_name = table_name
        self._store = store
        self._select = None
        self._filters: list[tuple[str, str, Any]] = []
        self._order = None
        self._limit = None
        self._payload: list[dict[str, Any]] | dict[str, Any] | None = None
        self._on_conflict = None

    # query chain methods
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

    def update(self, payload: Any) -> "FakeQuery":
        self._payload = payload
        return self

    # terminal
    def execute(self) -> Any:
        if self.table_name == "ml_predictions" and self._payload is not None:
            rows = cast(list[dict[str, Any]], self._payload)
            self._store.setdefault("ml_predictions", []).extend(rows)
            return types.SimpleNamespace(data=rows)
        if self.table_name == "ml_models" and self._payload is not None:
            # upsert model, return a row shape compatible with ModelVersionManager.save_model
            payload = cast(dict[str, Any], self._payload)
            row = {
                "id": payload.get("id", "model_1"),
                "tenant_id": payload.get("tenant_id", "t1"),
                "model_type": payload.get("model_type", "sales_forecasting"),
                "model_version": payload.get("model_version", "1.0"),
                "accuracy": payload.get("accuracy"),
                "created_at": "2024-01-01T00:00:00Z",
            }
            self._store.setdefault("ml_models", []).append(row)
            return types.SimpleNamespace(data=[row])
        # generic select
        if self.table_name == "ml_models" and self._select and any(f[0] == "eq" and f[1] == "is_active" and f[2] is True for f in self._filters):
            # Return empty to force initial training
            return types.SimpleNamespace(data=[])
        # negocios / others
        if self.table_name == "negocios":
            return types.SimpleNamespace(data=[{"id": "t1", "nombre": "Negocio 1"}])
        return types.SimpleNamespace(data=[])


class FakeSupabase:
    def __init__(self):
        self.store: dict[str, list[dict[str, Any]]] = {}

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(name, self.store)


@pytest.fixture()
def timeseries_60d() -> pd.DataFrame:
    # trend + weekly seasonality + noise
    days = pd.date_range(start=pd.Timestamp.today().normalize() - pd.Timedelta(days=59), periods=60, freq="D")
    t = np.arange(60)
    seasonal = 10 * np.sin(2 * np.pi * (t % 7) / 7)
    y = 100 + 0.5 * t + seasonal + np.random.normal(0, 2, size=60)
    return pd.DataFrame({"ds": days, "y": y})


def test_baseline_forecasts_shape(timeseries_60d: pd.DataFrame):
    eng = BusinessMLEngine()
    df1 = eng.forecast_baseline_naive(timeseries_60d, horizon_days=7)
    df2 = eng.forecast_baseline_snaive(timeseries_60d, horizon_days=7, season=7)
    for df in (df1, df2):
        assert set(["ds", "yhat", "yhat_lower", "yhat_upper"]).issubset(df.columns), "missing columns"
        assert len(df) == 7


def test_pipeline_cv_selects_and_triggers_drift(monkeypatch: pytest.MonkeyPatch, timeseries_60d: pd.DataFrame):
    fake = FakeSupabase()

    # Patch supabase clients in both pipeline and model_version_manager
    from app.services.ml import pipeline as pipe_mod
    from app.services.ml import model_version_manager as mvm_mod

    monkeypatch.setattr(pipe_mod, "get_supabase_service_client", lambda: fake)
    monkeypatch.setattr(mvm_mod, "get_supabase_service_client", lambda: fake)

    # Patch FeatureEngineer to return our series
    from app.services.ml import feature_engineer as fe_mod
    monkeypatch.setattr(fe_mod.FeatureEngineer, "sales_timeseries_daily", lambda self, tenant_id, days=365: timeseries_60d)

    # Capture notifications
    notified: list[tuple[str, str, dict]] = []
    class _N:
        @staticmethod
        def delay(business_id: str, notification_type: str, data: dict):
            notified.append((business_id, notification_type, data))
    from app.workers import notification_worker as nw
    monkeypatch.setattr(nw, "send_notification", types.SimpleNamespace(delay=_N.delay))

    # Force a very low threshold to trigger drift alert
    monkeypatch.setattr(ml_settings, "ML_ERROR_ALERT_MAPE", 1e-6)

    res = train_and_predict_sales(
        "t1",
        horizon_days=7,
        history_days=60,
        include_anomaly=False,
        model_candidates="naive,prophet",
        cv_folds=2,
    )

    assert isinstance(res, dict)
    ms = cast(dict[str, object], res.get("metrics_summary") or {})
    sel = cast(str, (res.get("selected_model") or ms.get("selected_model") or ""))
    assert sel in {"naive", "prophet"}
    assert "candidate_metrics" in ms
    # drift notification queued
    assert any(n[1] == "ml_drift_alert" for n in notified)


@pytest.mark.skipif(_importlib_util.find_spec("xgboost") is None, reason="xgboost not installed")
def test_xgboost_train_and_forecast(timeseries_60d: pd.DataFrame):
    eng = BusinessMLEngine()
    model = eng.train_xgboost(timeseries_60d)
    df = eng.forecast_sales_xgboost(model, timeseries_60d, horizon_days=7)
    assert set(["ds", "yhat", "yhat_lower", "yhat_upper"]).issubset(df.columns)
    assert len(df) == 7
