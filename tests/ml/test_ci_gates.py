import types
import numpy as np
import pandas as pd
import pytest
from typing import Any, cast

# Fallback import for IDE
try:
    from app.services.ml import pipeline as pl
except ModuleNotFoundError:  # pragma: no cover
    import sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from app.services.ml import pipeline as pl

# For naive baseline in MASE
try:
    from app.services.ml.ml_engine import BusinessMLEngine
except ModuleNotFoundError:  # pragma: no cover
    import sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from app.services.ml.ml_engine import BusinessMLEngine


class FakeQuery:
    def __init__(self, name: str, store: dict[str, list[dict[str, Any]]]):
        self.name = name
        self._store = store
        self._payload: list[dict[str, Any]] | dict[str, Any] | None = None
        self._on_conflict: str | None = None

    def upsert(self, payload: Any, on_conflict: str | None = None, returning: Any | None = None) -> "FakeQuery":
        self._payload = payload
        self._on_conflict = on_conflict
        return self

    def select(self, fields: str) -> "FakeQuery":
        return self

    def eq(self, field: str, value: Any) -> "FakeQuery":
        return self

    def order(self, field: str, desc: bool = False) -> "FakeQuery":
        return self

    def limit(self, n: int) -> "FakeQuery":
        return self

    def execute(self) -> Any:
        if self.name == "ml_predictions" and self._payload is not None:
            rows = cast(list[dict[str, Any]], self._payload)
            self._store.setdefault("ml_predictions", []).extend(rows)
            return types.SimpleNamespace(data=rows)
        if self.name == "ml_models" and self._payload is not None:
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
        return types.SimpleNamespace(data=[])


class FakeSupabase:
    def __init__(self) -> None:
        self.store: dict[str, list[dict[str, Any]]] = {}

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(name, self.store)


def _make_weekly_series(n: int = 180, mu: float = 100.0, sigma: float = 3.0, trend: float = 0.3, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=n, freq="D")
    t = np.arange(n)
    weekly = 5.0 * np.sin(2 * np.pi * (t % 7) / 7.0)
    y = mu + trend * t + weekly + rng.normal(0.0, sigma, size=n)
    return pd.DataFrame({"ds": idx, "y": y.astype(float)})


def _future_truth(n_hist: int, horizon: int, mu: float, sigma: float, trend: float, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(end=pd.Timestamp.today().normalize() + pd.Timedelta(days=horizon), periods=n_hist + horizon, freq="D")
    t = np.arange(n_hist + horizon)
    weekly = 5.0 * np.sin(2 * np.pi * (t % 7) / 7.0)
    y = mu + trend * t + weekly + rng.normal(0.0, sigma, size=n_hist + horizon)
    return pd.DataFrame({"ds": idx[-horizon:], "y": y[-horizon:].astype(float)})


def test_ci_gates_minimum_coverage_and_mase(monkeypatch: pytest.MonkeyPatch):
    fake = FakeSupabase()

    # Patch supabase clients everywhere
    import app.services.ml.pipeline as pipe_mod
    import app.services.ml.model_version_manager as mvm_mod
    import app.db.supabase_client as sc_mod
    monkeypatch.setattr(pipe_mod, "get_supabase_service_client", lambda: fake)
    monkeypatch.setattr(mvm_mod, "get_supabase_service_client", lambda: fake)
    monkeypatch.setattr(sc_mod, "get_supabase_service_client", lambda: fake)

    # Patch FeatureEngineer to deterministic series
    import app.services.ml.feature_engineer as fe_mod
    n_hist = 120
    mu = 100.0
    sigma = 3.0
    trend = 0.2
    series = _make_weekly_series(n=n_hist, mu=mu, sigma=sigma, trend=trend, seed=22)
    monkeypatch.setattr(fe_mod.FeatureEngineer, "sales_timeseries_daily", lambda self, bid, days=365: series)

    H = 7
    fake.store.clear()
    res = pl.train_and_predict_sales(
        business_id="tenant-ci",
        horizon_days=H,
        history_days=n_hist,
        include_anomaly=False,
        model_candidates="naive,snaive",
        cv_folds=2,
    )
    assert isinstance(res, dict) and res.get("trained") is True

    # Collect forecast rows
    rows_all = fake.store.get("ml_predictions", [])
    rows_fc = [r for r in rows_all if r.get("prediction_type") == "sales_forecast"]
    last = rows_fc[-H:]
    assert len(last) == H

    # Coverage gate vs future truth
    fut = _future_truth(n_hist=n_hist, horizon=H, mu=mu, sigma=sigma, trend=trend, seed=22)
    fut2 = fut.copy()
    fut2.loc[:, "date"] = pd.to_datetime(fut2["ds"]).dt.date.astype(str)
    covered = []
    for r in last:
        d = str(r.get("prediction_date"))
        pv = cast(dict[str, Any], r.get("predicted_values") or {})
        row = fut2.loc[fut2["date"] == d]
        if not row.empty:
            y = float(row.iloc[0]["y"])
            lo = float(pv.get("yhat_lower", np.nan))
            hi = float(pv.get("yhat_upper", np.nan))
            covered.append(float(lo <= y <= hi))
    cov = float(np.mean(covered)) if covered else 0.0
    assert cov >= 0.6

    # MASE gate vs naive baseline
    eng = BusinessMLEngine()
    fc_naive = eng.forecast_baseline_naive(series, horizon_days=H)
    fc_naive2 = fc_naive.copy()
    fc_naive2.loc[:, "date"] = pd.to_datetime(fc_naive2["ds"]).dt.date.astype(str)
    y_true = []
    yhat_model = []
    yhat_naive = []
    for r in last:
        d = str(r.get("prediction_date"))
        pv = cast(dict[str, Any], r.get("predicted_values") or {})
        row_t = fut2.loc[fut2["date"] == d]
        row_n = fc_naive2.loc[fc_naive2["date"] == d]
        if not row_t.empty and not row_n.empty:
            y_true.append(float(row_t.iloc[0]["y"]))
            yhat_model.append(float(pv.get("yhat", np.nan)))
            yhat_naive.append(float(row_n.iloc[0]["yhat"]))
    yt = np.asarray(y_true, dtype=float)
    ym = np.asarray(yhat_model, dtype=float)
    yn = np.asarray(yhat_naive, dtype=float)
    mae_m = float(np.nanmean(np.abs(yt - ym)))
    mae_n = float(np.nanmean(np.abs(yt - yn)))
    mase = mae_m / (mae_n + 1e-6)
    assert mase <= 1.2
