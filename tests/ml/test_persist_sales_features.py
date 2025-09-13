import types
import pandas as pd
import numpy as np
import pytest
from typing import Any

from app.services.ml.feature_engineer import FeatureEngineer


class FakeTable:
    def __init__(self, name: str) -> None:
        self.name = name
        self.upserts: list[tuple[list[dict[str, Any]] | dict[str, Any], str | None]] = []

    def upsert(self, data: Any, on_conflict: str | None = None, returning: Any | None = None) -> "FakeTable":
        self.upserts.append((data, on_conflict))
        return self

    def execute(self) -> Any:
        return types.SimpleNamespace(data=[])


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        if name not in self.tables:
            self.tables[name] = FakeTable(name)
        return self.tables[name]


def test_persist_sales_features_ma7_ma28_and_schema(monkeypatch: pytest.MonkeyPatch):
    # Patch service client used inside FeatureEngineer
    import app.services.ml.feature_engineer as fe_mod
    fake = FakeSupabase()
    monkeypatch.setattr(fe_mod, "get_supabase_service_client", lambda: fake)

    # Build a simple daily series with 10 days
    ds = pd.date_range("2024-01-01", periods=10, freq="D").date
    y = np.arange(1, 11, dtype=float)  # 1..10
    daily_ts = pd.DataFrame({"ds": ds, "y": y})

    fe = FeatureEngineer()
    rows = fe.persist_sales_features("tenantA", daily_ts)

    # Validate rows count
    assert rows == 10
    # Validate upserted schema and values
    tbl = fake.tables.get("ml_features")
    assert tbl is not None, "ml_features table not used"
    # Only one batch upsert expected
    assert len(tbl.upserts) == 1
    data, on_conflict = tbl.upserts[0]
    assert on_conflict == "tenant_id,feature_date,feature_type"
    assert isinstance(data, list) and len(data) == 10

    # Compute expected moving averages
    exp_ma7 = pd.Series(y).rolling(window=7, min_periods=1).mean().to_numpy()
    exp_ma28 = pd.Series(y).rolling(window=28, min_periods=1).mean().to_numpy()

    for i, rec in enumerate(data):
        assert rec["tenant_id"] == "tenantA"
        assert rec["feature_type"] == "sales_metrics"
        assert rec["feature_date"] == str(ds[i])
        feats = rec["features"]
        assert set(feats.keys()) == {"daily_total", "ma7", "ma28"}
        assert abs(float(feats["daily_total"]) - float(y[i])) < 1e-9
        assert abs(float(feats["ma7"]) - float(exp_ma7[i])) < 1e-9
        assert abs(float(feats["ma28"]) - float(exp_ma28[i])) < 1e-9
