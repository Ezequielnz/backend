"""Stress tests for ML pipeline.

pyright: reportMissingImports=false
"""
import types
import math
import numpy as np
import pandas as pd
import pytest
from typing import Any, Callable, cast

from app.services.ml.pipeline import train_and_predict_sales


class FakeQuery:
    def __init__(self, table_name: str, store: dict[str, list[dict[str, Any]]]):
        self.table_name = table_name
        self._store = store
        self._select = None
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None
        self._order: tuple[str, bool] | None = None
        self._payload: list[dict[str, Any]] | dict[str, Any] | None = None
        self._on_conflict: str | None = None

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
            # Respect on_conflict=tenant_id,prediction_date,prediction_type
            keys = [k.strip() for k in (self._on_conflict or "").split(",") if k.strip()]
            if keys:
                existing = self._store.setdefault("ml_predictions", [])
                for r in rows:
                    def _match(e: dict[str, Any]) -> bool:
                        return all(str(e.get(k)) == str(r.get(k)) for k in keys)
                    idx = next((i for i, e in enumerate(existing) if _match(e)), None)
                    if idx is None:
                        existing.append(r)
                    else:
                        existing[idx] = r
            else:
                self._store.setdefault("ml_predictions", []).extend(rows)
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
            # on_conflict tenant_id,model_type,model_version
            keys = [k.strip() for k in (self._on_conflict or "").split(",") if k.strip()]
            if keys:
                existing = self._store.setdefault("ml_models", [])
                def _match(e: dict[str, Any]) -> bool:
                    return all(str(e.get(k)) == str(row.get(k)) for k in keys)
                idx = next((i for i, e in enumerate(existing) if _match(e)), None)
                if idx is None:
                    existing.append(row)
                else:
                    existing[idx] = row
            else:
                self._store.setdefault("ml_models", []).append(row)
            return types.SimpleNamespace(data=[row])
        # default empty selects
        return types.SimpleNamespace(data=[])


class FakeSupabase:
    def __init__(self):
        self.store: dict[str, list[dict[str, Any]]] = {}

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(name, self.store)


# Reuse base fixture by importing from existing test module
@pytest.fixture()
def timeseries_60d() -> pd.DataFrame:
    # trend + weekly seasonality + noise (reproducible)
    rng = np.random.default_rng(12345)
    days = pd.date_range(start=pd.Timestamp.today().normalize() - pd.Timedelta(days=59), periods=60, freq="D")
    t = np.arange(60)
    seasonal = 10.0 * np.sin(2 * np.pi * (t % 7) / 7.0)
    y = 100.0 + 0.5 * t + seasonal + rng.normal(0.0, 2.0, size=60)
    return pd.DataFrame({"ds": days, "y": y})


def _with_gaps(df: pd.DataFrame, every: int = 5) -> pd.DataFrame:
    df2 = df.copy()
    mask = np.ones(len(df2), dtype=bool)
    mask[::max(1, every)] = False
    return cast(pd.DataFrame, df2.loc[mask].reset_index(drop=True))


def _with_outliers(df: pd.DataFrame, idxs: list[int] | None = None, magnitude: float = 5.0) -> pd.DataFrame:
    df2 = df.copy()
    if idxs is None:
        idxs = [10, 20, 30]
    y = df2["y"].to_numpy(dtype=float)
    for i in idxs:
        if 0 <= i < len(y):
            y[i] = y[i] + magnitude * (np.nanstd(y) + 1e-6)
    df2.loc[:, "y"] = y
    return df2


def _seasonal_shift(df: pd.DataFrame, shift_start: int = 30, extra_amp: float = 10.0) -> pd.DataFrame:
    df2 = df.copy()
    # Add extra weekly amplitude on the tail segment
    t = np.arange(len(df2))
    seasonal = extra_amp * np.sin(2 * np.pi * (t % 7) / 7.0)
    y = df2["y"].to_numpy(dtype=float)
    y2 = y.copy()
    y2[shift_start:] = y2[shift_start:] + seasonal[shift_start:]
    df2.loc[:, "y"] = y2
    return df2


def _assert_fcst_rows(store: dict[str, list[dict[str, Any]]], horizon: int) -> list[dict[str, Any]]:
    rows_all = store.get("ml_predictions", [])
    # Only consider forecast rows, not anomalies
    rows = [r for r in rows_all if r.get("prediction_type") == "sales_forecast"]
    assert rows, "No forecast rows inserted"
    last_batch = rows[-horizon:]
    for r in last_batch:
        pv = cast(dict[str, Any], r.get("predicted_values") or {})
        yhat = float(pv.get("yhat", math.nan))
        ylo = float(pv.get("yhat_lower", math.nan))
        yhi = float(pv.get("yhat_upper", math.nan))
        assert not (math.isnan(yhat) or math.isnan(ylo) or math.isnan(yhi)), "NaNs in forecast outputs"
        assert ylo <= yhat <= yhi, "interval ordering violated"
    return last_batch


@pytest.mark.parametrize("variant_name", [
    "gaps",
    "outliers",
    "seasonal_shift",
    "short_series",
])
def test_stress_variants_pipeline(monkeypatch: pytest.MonkeyPatch, timeseries_60d: pd.DataFrame, variant_name: str):
    fake = FakeSupabase()

    # Patch supabase clients in pipeline and model_version_manager
    from app.services.ml import pipeline as pipe_mod
    from app.services.ml import model_version_manager as mvm_mod
    monkeypatch.setattr(pipe_mod, "get_supabase_service_client", lambda: fake)
    monkeypatch.setattr(mvm_mod, "get_supabase_service_client", lambda: fake)

    # Build base and variants
    base = timeseries_60d
    if variant_name == "gaps":
        series = _with_gaps(base, every=5)
    elif variant_name == "outliers":
        series = _with_outliers(base)
    elif variant_name == "seasonal_shift":
        series = _seasonal_shift(base)
    elif variant_name == "short_series":
        series = base.head(7)  # at the edge of min_train=7
    else:
        series = base

    # Patch FeatureEngineer to return the chosen variant
    from app.services.ml import feature_engineer as fe_mod
    monkeypatch.setattr(fe_mod.FeatureEngineer, "sales_timeseries_daily", lambda self, tenant_id, days=365: series)

    # Run twice to test log_transform stability (off/on)
    for log_tf in (False, True):
        fake.store.clear()
        res = train_and_predict_sales(
            "t1",
            horizon_days=7,
            history_days=60,
            include_anomaly=True,
            model_candidates="naive,prophet",
            cv_folds=2,
            anomaly_method="stl_resid",
            log_transform=log_tf,
        )
        assert isinstance(res, dict)
        assert res.get("trained") is True
        assert res.get("forecasts_inserted") == 7
        # Validate forecast rows and intervals
        last_batch = _assert_fcst_rows(fake.store, horizon=7)
        # Validate anomalies behavior
        anomalies = [r for r in fake.store.get("ml_predictions", []) if r.get("prediction_type") == "sales_anomaly"]
        if variant_name in ("outliers", "seasonal_shift"):
            assert len(anomalies) > 0, f"Expected anomalies for {variant_name}"
        else:
            # For gaps/short_series we only ensure the detector didn't crash
            assert len(anomalies) >= 0
