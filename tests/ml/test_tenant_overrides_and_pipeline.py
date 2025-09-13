import types
import pytest
import numpy as np
import pandas as pd
from typing import Any, Callable, cast

from app.config.ml_settings import ml_settings
from app.services.ml import pipeline as pl


class TenantSettingsTable:
    def __init__(self, settings_map: dict[str, dict[str, Any]]):
        self.settings_map = settings_map
        self._select: str | None = None
        self._tenant: str | None = None
        self._limit: int | None = None

    def select(self, fields: str) -> "TenantSettingsTable":
        self._select = fields
        return self

    def eq(self, field: str, value: Any) -> "TenantSettingsTable":
        if field == "tenant_id":
            self._tenant = cast(str, value)
        return self

    def limit(self, n: int) -> "TenantSettingsTable":
        self._limit = n
        return self

    def execute(self) -> Any:
        data: list[dict[str, Any]] = []
        if self._tenant and self._tenant in self.settings_map:
            data = [{"settings": self.settings_map[self._tenant]}]
        return types.SimpleNamespace(data=data)


class SimpleTable:
    def __init__(self, name: str, store: dict[str, list[dict[str, Any]]]):
        self.name = name
        self.store = store
        self._payload: Any = None
        self._on_conflict: str | None = None
        self._select: str | None = None

    # Minimal API used by code paths under test
    def upsert(self, payload: Any, on_conflict: str | None = None, returning: Any | None = None) -> "SimpleTable":
        self._payload = payload
        self._on_conflict = on_conflict
        # Simulate effect of upsert: write payload to store for inspection
        rows = payload if isinstance(payload, list) else [payload]
        self.store.setdefault(self.name, []).extend(rows)
        return self

    def select(self, fields: str) -> "SimpleTable":
        self._select = fields
        return self

    def eq(self, field: str, value: Any) -> "SimpleTable":
        # Not needed for this simple test path except for model_id fetch inside worker (not used here)
        return self

    def limit(self, n: int) -> "SimpleTable":
        return self

    def order(self, field: str, desc: bool = False) -> "SimpleTable":
        return self

    def execute(self) -> Any:
        # For ml_models upsert, simulate DB returning inserted row with id
        if self.name == "ml_models" and self._payload is not None:
            row = self._payload if isinstance(self._payload, dict) else self._payload[0]
            # Add generated fields
            row = dict(row)
            row.setdefault("id", f"mdl_{len(self.store.get(self.name, []))}")
            row.setdefault("created_at", "2024-01-01T00:00:00Z")
            # Replace last written row with enriched fields
            self.store[self.name][-1] = row
            return types.SimpleNamespace(data=[row])
        return types.SimpleNamespace(data=self.store.get(self.name, []))


class FakeSupabase:
    def __init__(self, settings_map: dict[str, dict[str, Any]] | None = None):
        self.store: dict[str, list[dict[str, Any]]] = {}
        self.settings_map = settings_map or {}

    def table(self, name: str) -> Any:
        if name == "tenant_ml_settings":
            return TenantSettingsTable(self.settings_map)
        return SimpleTable(name, self.store)


def _make_stable_weekly_series(days: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=days, freq="D")
    t = np.arange(days)
    weekly = 20.0 + 5.0 * np.sin(2 * np.pi * (t % 7) / 7.0)
    noise = rng.normal(0, 0.8, size=days)
    y = weekly + noise
    return pd.DataFrame({"ds": idx.date, "y": y.astype(float)})


def test_get_tenant_overrides(monkeypatch: pytest.MonkeyPatch):
    from app.config import ml_settings as ml_mod
    fake = FakeSupabase({
        "tenant-123": {
            "ML_CV_FOLDS": 5,
            "ML_MODEL_CANDIDATES": "naive,snaive",
            "ML_SEASONALITY_MODE": "multiplicative",
            "ML_HOLIDAYS_COUNTRY": "AR",
        }
    })
    monkeypatch.setattr(ml_mod, "get_supabase_service_client", lambda: fake)

    overrides = ml_settings.get_tenant_overrides("tenant-123")
    assert overrides["ML_CV_FOLDS"] == 5
    assert overrides["ML_MODEL_CANDIDATES"] == "naive,snaive"
    assert overrides["ML_SEASONALITY_MODE"] == "multiplicative"
    assert overrides["ML_HOLIDAYS_COUNTRY"] == "AR"


def test_pipeline_saves_hyperparams_reflecting_overrides(monkeypatch: pytest.MonkeyPatch):
    # Patch Supabase clients used by pipeline and model_version_manager to our fake
    import app.services.ml.pipeline as pipe_mod
    import app.services.ml.model_version_manager as mvm_mod
    fake = FakeSupabase()
    monkeypatch.setattr(pipe_mod, "get_supabase_service_client", lambda: fake)
    monkeypatch.setattr(mvm_mod, "get_supabase_service_client", lambda: fake)

    # Patch tenant overrides at the pipeline's ml_settings singleton
    overrides = {
        "ML_CV_FOLDS": 2,
        "ML_MODEL_CANDIDATES": "naive",
        "ML_SELECT_BEST": True,
        "ML_CV_PRIMARY_METRIC": "mape",
        "ML_SEASONALITY_MODE": "multiplicative",
        "ML_HOLIDAYS_COUNTRY": "AR",
        "ML_ANOMALY_METHOD": "iforest",
        "ML_STL_PERIOD": 7,
        "ML_STL_ZTHRESH": 2.5,
    }
    # Patch on the MLSettings class, not the instance
    monkeypatch.setattr(pipe_mod.ml_settings.__class__, "get_tenant_overrides", lambda self, tenant_id: overrides)

    # Patch FeatureEngineer to return a stable series
    import app.services.ml.feature_engineer as fe_mod
    monkeypatch.setattr(fe_mod.FeatureEngineer, "sales_timeseries_daily", lambda self, bid, days=120: _make_stable_weekly_series(days, 42))

    # Run pipeline with include_anomaly=False (faster) and small horizon
    res = pl.train_and_predict_sales(
        business_id="tenant-ovr",
        horizon_days=7,
        history_days=90,
        include_anomaly=False,
    )
    assert res.get("trained") is True
    assert res.get("selected_model") in ("naive", "snaive")  # with naive only, must be naive

    # Inspect saved model row to verify hyperparameters reflect overrides
    rows = fake.store.get("ml_models", [])
    assert rows, "ml_models should have a saved row"
    saved = rows[-1]
    hypers = saved.get("hyperparameters", {})
    assert hypers["cv_folds"] == 2
    assert hypers["seasonality_mode"] == "multiplicative"
    assert hypers["holidays_country"] == "AR"
    assert hypers["cv_primary_metric"] == "mape"
    assert hypers["model_candidates"] == ["naive"]
    # If baseline selected, variant must be recorded
    if res.get("selected_model") in ("naive", "snaive"):
        assert hypers["baseline_variant"] == res.get("selected_model")


def test_holdout_stability_across_periods(monkeypatch: pytest.MonkeyPatch):
    # Fake supabase for pipeline/model manager
    import app.services.ml.pipeline as pipe_mod
    import app.services.ml.model_version_manager as mvm_mod
    fake = FakeSupabase()
    monkeypatch.setattr(pipe_mod, "get_supabase_service_client", lambda: fake)
    monkeypatch.setattr(mvm_mod, "get_supabase_service_client", lambda: fake)

    # Force candidates to naive only for deterministic metrics
    # Patch on the MLSettings class, not the instance
    monkeypatch.setattr(pipe_mod.ml_settings.__class__, "get_tenant_overrides", lambda self, tenant_id: {
        "ML_MODEL_CANDIDATES": "naive",
        "ML_SELECT_BEST": True,
        "ML_CV_PRIMARY_METRIC": "mape",
        "ML_CV_FOLDS": 2,
    })

    # Provide two similar but not identical periods by alternating seeds
    call_state = {"k": 0}

    def _series_for_call(self, bid: str, days: int = 120):
        seed = 100 if call_state["k"] == 0 else 101
        return _make_stable_weekly_series(days, seed)

    import app.services.ml.feature_engineer as fe_mod
    monkeypatch.setattr(fe_mod.FeatureEngineer, "sales_timeseries_daily", _series_for_call)

    # First run
    call_state["k"] = 0
    res1 = pl.train_and_predict_sales("tenant-stab", horizon_days=7, history_days=120, include_anomaly=False)
    mape1 = float(res1.get("metrics_summary", {}).get("mape", 0.5))

    # Second run (different period)
    call_state["k"] = 1
    res2 = pl.train_and_predict_sales("tenant-stab", horizon_days=7, history_days=120, include_anomaly=False)
    mape2 = float(res2.get("metrics_summary", {}).get("mape", 0.5))

    # Expect stability: difference bounded
    assert abs(mape1 - mape2) <= 0.1, f"MAPE stability failed: {mape1:.3f} vs {mape2:.3f}"
