import numpy as np
import pandas as pd
import pytest
from typing import Any

from app.services.ml import pipeline as pl


def _make_linear_ts(n: int = 100) -> pd.DataFrame:
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=n, freq="D")
    y = np.linspace(10.0, 20.0, n)
    return pd.DataFrame({"ds": idx.date, "y": y})


def test_forward_chaining_splits_no_future(monkeypatch: pytest.MonkeyPatch):
    # Patch Supabase deps to a richer fake that returns rows for ml_models upsert
    import app.services.ml.pipeline as pipe_mod
    import app.services.ml.model_version_manager as mvm_mod

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
                return type("R", (), {"data": [row]})()
            return type("R", (), {"data": self.store.get(self.name, [])})()

    class FakeSupabase:
        def __init__(self) -> None:
            self.store: dict[str, list[dict[str, Any]]] = {}
        def table(self, name: str) -> Any:
            return SimpleTable(name, self.store)

    fake = FakeSupabase()
    monkeypatch.setattr(pipe_mod, "get_supabase_service_client", lambda: fake)
    monkeypatch.setattr(mvm_mod, "get_supabase_service_client", lambda: fake)

    # Provide synthetic series via FeatureEngineer and avoid real client creation
    import app.services.ml.feature_engineer as fe_mod
    monkeypatch.setattr(fe_mod, "get_supabase_service_client", lambda: fake)
    ts = _make_linear_ts(100)
    monkeypatch.setattr(fe_mod.FeatureEngineer, "sales_timeseries_daily", lambda self, bid, days=120: ts)

    # Force Prophet-only candidate with 3 folds and horizon=7
    monkeypatch.setattr(pipe_mod.ml_settings.__class__, "get_tenant_overrides", lambda self, tenant_id: {
        "ML_MODEL_CANDIDATES": "prophet",
        "ML_SELECT_BEST": True,
        "ML_CV_FOLDS": 3,
    })

    res = pl.train_and_predict_sales("tenant-leak", horizon_days=7, history_days=100, include_anomaly=False)
    cv = res.get("metrics_summary", {}).get("cv", {})
    folds = int(cv.get("folds", 0))
    assert folds == 3
    per_fold = cv.get("metrics_per_fold", [])
    assert isinstance(per_fold, list) and len(per_fold) == folds

    # expected train sizes: n - i*horizon for i=3..1
    n = 100
    H = 7
    expected_train = [n - i * H for i in range(folds, 0, -1)]
    got_train = [int(round(f.get("train_rows", -1))) for f in per_fold]
    got_test = [int(round(f.get("test_rows", -1))) for f in per_fold]
    assert got_train == expected_train
    assert all(t == H for t in got_test), f"test_rows must equal horizon {H} in all folds"
