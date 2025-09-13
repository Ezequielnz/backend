import types
import pandas as pd
import numpy as np
import pytest
import importlib.util as _importlib_util

from typing import Any, cast

# Under test
from app.services.ml.pipeline import train_and_predict_sales


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
        self._single = False

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

    def single(self) -> "FakeQuery":
        self._single = True
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


def _make_synth_series(n: int = 90, seed: int = 123) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.date_range(start=pd.Timestamp.today().normalize() - pd.Timedelta(days=n - 1), periods=n, freq="D")
    t = np.arange(n)
    seasonal = 10.0 * np.sin(2 * np.pi * (t % 7) / 7.0)
    trend = 0.4 * t
    noise = rng.normal(0.0, 2.0, size=n)
    y = 100.0 + trend + seasonal + noise
    return pd.DataFrame({"ds": days, "y": y})


@pytest.mark.parametrize("horizon_days", [7, 14, 28])
@pytest.mark.parametrize("cv_folds", [2, 3])
def test_cv_multi_horizon_comparison(monkeypatch: pytest.MonkeyPatch, horizon_days: int, cv_folds: int):
    # Arrange
    fake = FakeSupabase()

    # Patch supabase clients in pipeline and model_version_manager
    from app.services.ml import pipeline as pipe_mod
    from app.services.ml import model_version_manager as mvm_mod

    monkeypatch.setattr(pipe_mod, "get_supabase_service_client", lambda: fake)
    monkeypatch.setattr(mvm_mod, "get_supabase_service_client", lambda: fake)

    # Patch FeatureEngineer to return synthetic series consistently
    from app.services.ml import feature_engineer as fe_mod
    monkeypatch.setattr(fe_mod.FeatureEngineer, "sales_timeseries_daily", lambda self, tenant_id, days=365: _make_synth_series(n=90, seed=42))

    # Build candidates (optionally include xgboost if installed)
    base_candidates = ["naive", "snaive", "prophet", "sarimax"]
    if _importlib_util.find_spec("xgboost") is not None:
        base_candidates.append("xgboost")
    candidates_str = ",".join(base_candidates)

    # Act
    res = train_and_predict_sales(
        "t1",
        horizon_days=horizon_days,
        history_days=90,
        include_anomaly=False,
        model_candidates=candidates_str,
        cv_folds=cv_folds,
    )

    # Assert basic structure
    assert isinstance(res, dict)
    assert res.get("trained") is True
    ms = cast(dict[str, Any], res.get("metrics_summary") or {})

    # 1) Ensure candidate_metrics present for all candidates requested
    cand_metrics = cast(dict[str, Any], ms.get("candidate_metrics") or {})
    missing = [c for c in base_candidates if c not in cand_metrics]
    assert not missing, f"Missing candidate metrics for: {missing}"

    # 2) Forecast payload coherence with horizon
    assert res.get("forecasts_inserted") == horizon_days

    # 3) Validate rows inserted in fake store match horizon and schema
    rows = fake.store.get("ml_predictions", [])
    assert len(rows) >= horizon_days  # could accumulate across runs; check at least this run's horizon
    last_batch = rows[-horizon_days:]
    assert all(r.get("prediction_type") == "sales_forecast" for r in last_batch)
    # ensure predicted_values contains normalized keys
    for r in last_batch:
        pv = cast(dict[str, Any], r.get("predicted_values") or {})
        assert set(["yhat", "yhat_lower", "yhat_upper"]).issubset(pv.keys())
        # basic range sanity: lower <= upper (yhat may be outside if intervals degenerate, but usually within)
        assert float(pv.get("yhat_lower", 0.0)) <= float(pv.get("yhat_upper", 0.0))
