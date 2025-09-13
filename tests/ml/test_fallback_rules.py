import types
import numpy as np
import pandas as pd
import pytest
from typing import Any

from app.services.ml import pipeline as pl


class DummyProphet:
    pass


class SimpleTable:
    def __init__(self, name: str, store: dict[str, list[dict[str, Any]]]):
        self.name = name
        self.store = store
        self._payload: Any = None
        self._on_conflict: str | None = None

    def upsert(self, payload: Any, on_conflict: str | None = None, returning: Any | None = None) -> "SimpleTable":
        self._payload = payload
        self._on_conflict = on_conflict
        rows = payload if isinstance(payload, list) else [payload]
        self.store.setdefault(self.name, []).extend(rows)
        return self

    def execute(self) -> Any:
        if self.name == "ml_models" and self._payload is not None:
            row = self._payload if isinstance(self._payload, dict) else self._payload[0]
            row = dict(row)
            row.setdefault("id", f"mdl_{len(self.store.get(self.name, []))}")
            row.setdefault("created_at", "2024-01-01T00:00:00Z")
            self.store[self.name][-1] = row
            return types.SimpleNamespace(data=[row])
        return types.SimpleNamespace(data=self.store.get(self.name, []))


class FakeSupabase:
    def __init__(self) -> None:
        self.store: dict[str, list[dict[str, Any]]] = {}

    def table(self, name: str) -> Any:
        return SimpleTable(name, self.store)


def _simple_ts(n: int = 60) -> pd.DataFrame:
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=n, freq="D")
    y = np.linspace(10.0, 15.0, n)
    return pd.DataFrame({"ds": idx.date, "y": y})


def test_xgboost_fallbacks_to_prophet_when_only_xgb(monkeypatch: pytest.MonkeyPatch):
    import app.services.ml.pipeline as pipe_mod
    import app.services.ml.model_version_manager as mvm_mod
    import app.services.ml.ml_engine as eng_mod
    import app.services.ml.feature_engineer as fe_mod
    import app.services.ml.model_version_manager as mvm_mod
    from app.config.ml_settings import ml_settings as settings

    fake = FakeSupabase()
    monkeypatch.setattr(pipe_mod, "get_supabase_service_client", lambda: fake)
    monkeypatch.setattr(mvm_mod, "get_supabase_service_client", lambda: fake)
    monkeypatch.setattr(fe_mod, "get_supabase_service_client", lambda: fake)
    # Avoid Celery drift alerts (Redis)
    monkeypatch.setattr(settings, "ML_ERROR_ALERT_MAPE", 9999.0)
    # Avoid pickling errors for dummy model
    monkeypatch.setattr(mvm_mod.ModelVersionManager, "_serialize", lambda self, model: b"noop")

    # Series
    ts = _simple_ts(80)
    monkeypatch.setattr(fe_mod.FeatureEngineer, "sales_timeseries_daily", lambda self, bid, days=120: ts)

    # Force candidates to only xgboost
    monkeypatch.setattr(pipe_mod.ml_settings.__class__, "get_tenant_overrides", lambda self, tenant_id: {
        "ML_MODEL_CANDIDATES": "xgboost",
        "ML_SELECT_BEST": True,
        "ML_CV_FOLDS": 2,
    })

    # Make xgboost training fail, and stub prophet training/forecast to be lightweight
    def _fail_xgb(self, daily_ts: pd.DataFrame):
        raise ImportError("xgboost not installed")
    monkeypatch.setattr(eng_mod.BusinessMLEngine, "train_xgboost", _fail_xgb)

    # Return a dummy model and a trivial forecast
    monkeypatch.setattr(eng_mod.BusinessMLEngine, "train_sales_forecasting_prophet", lambda self, ts, seasonality_mode="additive", holidays_country="": DummyProphet())
    def _fc_prophet(self, model, horizon_days: int = 14):
        idx = pd.date_range(start=pd.Timestamp.today().normalize() + pd.Timedelta(days=1), periods=horizon_days, freq="D")
        return pd.DataFrame({"ds": idx, "yhat": np.ones(horizon_days)*ts["y"].iloc[-1], "yhat_lower": np.ones(horizon_days)*ts["y"].iloc[-1], "yhat_upper": np.ones(horizon_days)*ts["y"].iloc[-1]})
    monkeypatch.setattr(eng_mod.BusinessMLEngine, "forecast_sales_prophet", _fc_prophet)

    res = pl.train_and_predict_sales("tenant-fallback", horizon_days=7, history_days=60, include_anomaly=False)
    assert res.get("trained") is True
    # After fallback, selected_model must be prophet
    assert res.get("selected_model") == "prophet"
    # Hyperparameters should reflect selected model
    rows = fake.store.get("ml_models", [])
    assert rows and rows[-1].get("hyperparameters", {}).get("selected_model") == "prophet"


def test_xgboost_failure_selects_baseline_if_available(monkeypatch: pytest.MonkeyPatch):
    import app.services.ml.pipeline as pipe_mod
    import app.services.ml.model_version_manager as mvm_mod
    import app.services.ml.ml_engine as eng_mod
    import app.services.ml.feature_engineer as fe_mod

    fake = FakeSupabase()
    monkeypatch.setattr(pipe_mod, "get_supabase_service_client", lambda: fake)
    monkeypatch.setattr(mvm_mod, "get_supabase_service_client", lambda: fake)
    monkeypatch.setattr(fe_mod, "get_supabase_service_client", lambda: fake)

    ts = _simple_ts(80)
    monkeypatch.setattr(fe_mod.FeatureEngineer, "sales_timeseries_daily", lambda self, bid, days=120: ts)

    # Candidates include baseline
    monkeypatch.setattr(pipe_mod.ml_settings.__class__, "get_tenant_overrides", lambda self, tenant_id: {
        "ML_MODEL_CANDIDATES": "xgboost,naive",
        "ML_SELECT_BEST": True,
        "ML_CV_FOLDS": 2,
    })

    # Fail xgboost train
    monkeypatch.setattr(eng_mod.BusinessMLEngine, "train_xgboost", lambda self, ts: (_ for _ in ()).throw(ImportError("no xgb")))

    res = pl.train_and_predict_sales("tenant-fallback2", horizon_days=7, history_days=60, include_anomaly=False)
    assert res.get("trained") is True
    # With xgb failing and naive available, selection should choose naive (no heavy prophet call)
    assert res.get("selected_model") in ("naive", "snaive")
