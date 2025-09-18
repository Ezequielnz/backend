import types
import numpy as np
import pandas as pd
import pytest
from typing import Any, cast

# Fallback import for IDE standalone execution
try:
    from app.services.ml import pipeline as pl
except ModuleNotFoundError:  # pragma: no cover
    import sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from app.services.ml import pipeline as pl


class FakeQuery:
    def __init__(self, name: str, store: dict[str, list[dict[str, Any]]]):
        self.name = name
        self._store = store
        self._payload: list[dict[str, Any]] | dict[str, Any] | None = None
        self._on_conflict: str | None = None
        self._select: str | None = None
        self._filters: list[tuple[str, str, Any]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def select(self, fields: str) -> "FakeQuery":
        self._select = fields
        return self

    def eq(self, field: str, value: Any) -> "FakeQuery":
        self._filters.append(("eq", field, value))
        return self

    def order(self, field: str, desc: bool = False) -> "FakeQuery":
        self._order = (field, desc)
        return self

    def limit(self, n: int) -> "FakeQuery":
        self._limit = n
        return self

    def upsert(self, payload: Any, on_conflict: str | None = None, returning: Any | None = None) -> "FakeQuery":
        self._payload = payload
        self._on_conflict = on_conflict
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


def _future_weekly_truth(n_hist: int, horizon: int, mu: float = 100.0, sigma: float = 3.0, trend: float = 0.3, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    # Recreate same process and generate n_hist + horizon, with end at today+h so that
    # the last horizon dates align with forecast dates (tomorrow..tomorrow+h-1)
    idx = pd.date_range(end=pd.Timestamp.today().normalize() + pd.Timedelta(days=horizon), periods=n_hist + horizon, freq="D")
    t = np.arange(n_hist + horizon)
    weekly = 5.0 * np.sin(2 * np.pi * (t % 7) / 7.0)
    y = mu + trend * t + weekly + rng.normal(0.0, sigma, size=n_hist + horizon)
    fut = pd.DataFrame({"ds": idx[-horizon:], "y": y[-horizon:].astype(float)})
    return fut


def test_export_contract_and_gates(monkeypatch: pytest.MonkeyPatch):
    fake = FakeSupabase()
    # Patch pipeline and model manager clients
    import app.services.ml.pipeline as pipe_mod
    import app.services.ml.model_version_manager as mvm_mod
    import app.db.supabase_client as sc_mod
    monkeypatch.setattr(pipe_mod, "get_supabase_service_client", lambda: fake)
    monkeypatch.setattr(mvm_mod, "get_supabase_service_client", lambda: fake)
    monkeypatch.setattr(sc_mod, "get_supabase_service_client", lambda: fake)

    # Patch FeatureEngineer to return deterministic series
    import app.services.ml.feature_engineer as fe_mod
    n_hist = 120
    mu = 100.0
    sigma = 3.0
    trend = 0.3
    series = _make_weekly_series(n=n_hist, mu=mu, sigma=sigma, trend=trend, seed=99)
    monkeypatch.setattr(fe_mod.FeatureEngineer, "sales_timeseries_daily", lambda self, bid, days=365: series)

    H = 7
    res = pl.train_and_predict_sales(
        business_id="tenant-export",
        horizon_days=H,
        history_days=n_hist,
        include_anomaly=False,
        model_candidates="naive",
        cv_folds=2,
    )

    assert isinstance(res, dict)
    assert res.get("trained") is True
    # Contract: selected_model and metrics_summary present
    ms = cast(dict[str, Any], res.get("metrics_summary") or {})
    assert "selected_model" in res
    assert "candidate_metrics" in ms

    # Contract: ml_predictions contain forecast rows with required fields
    rows_all = fake.store.get("ml_predictions", [])
    rows_fc = [r for r in rows_all if r.get("prediction_type") == "sales_forecast"]
    assert len(rows_fc) >= H
    last = rows_fc[-H:]
    for r in last:
        pv = cast(dict[str, Any], r.get("predicted_values") or {})
        assert set(["yhat", "yhat_lower", "yhat_upper"]).issubset(pv.keys())

    # CI gate: coverage on future truth should be reasonable (lenient threshold)
    fut = _future_weekly_truth(n_hist=n_hist, horizon=H, mu=mu, sigma=sigma, trend=trend, seed=99)
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
    # Gate: coverage >= 0.6 (lenient, avoids flakiness across envs)
    assert cov >= 0.6, f"CI coverage gate failed: {cov:.3f} < 0.60"
