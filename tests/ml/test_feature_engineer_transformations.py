import pandas as pd
import pytest
from decimal import Decimal
from typing import Any, cast

from app.services.ml.feature_engineer import FeatureEngineer


def test_sales_timeseries_daily_fills_missing_and_parses_tz(monkeypatch: pytest.MonkeyPatch):
    # Arrange synthetic raw ventas rows with a missing middle day and mixed tz/naive datetimes
    rows: list[dict[str, Any]] = [
        {"id": "1", "negocio_id": "t1", "fecha": "2024-01-01T10:00:00+00:00", "total": "10.5"},
        {"id": "2", "negocio_id": "t1", "fecha": "2024-01-03T23:59:59+00:00", "total": 5},
    ]

    # Patch DB access so FE doesn't hit Supabase
    monkeypatch.setattr(
        FeatureEngineer,
        "get_sales_rows",
        lambda self, tenant_id, timerange=None: rows,
    )

    fe = FeatureEngineer()

    # Act
    ts = fe.sales_timeseries_daily("t1", days=3)

    # Assert
    assert list(ts.columns) == ["ds", "y"], "Output columns must be ds,y"
    # Validate that aggregation by day works and middle day is either filled as 0 or series contains endpoints
    ds_str = [str(d) for d in cast(list, ts["ds"].astype(str).tolist())]
    y_vals = [float(v) for v in ts["y"].tolist()]
    assert len(ds_str) >= 2
    # Build mapping for easy checks
    day_to_y = {ds_str[i]: y_vals[i] for i in range(len(ds_str))}
    assert abs(day_to_y.get("2024-01-01", -1.0) - 10.5) < 1e-9
    assert abs(day_to_y.get("2024-01-03", -1.0) - 5.0) < 1e-9
    # If the middle day is present, it should be zero-filled
    if "2024-01-02" in day_to_y:
        assert abs(day_to_y["2024-01-02"] - 0.0) < 1e-9


def test_sales_timeseries_daily_numeric_and_imputation(monkeypatch: pytest.MonkeyPatch):
    # rows including Decimal, empty string, and None should coerce to floats; missing day fills with 0
    rows: list[dict[str, Any]] = [
        {"id": "1", "negocio_id": "t1", "fecha": "2024-02-01T01:00:00Z", "total": Decimal("3.50")},
        {"id": "2", "negocio_id": "t1", "fecha": "2024-02-01T18:30:00Z", "total": "1.50"},
        {"id": "3", "negocio_id": "t1", "fecha": "2024-02-03T12:00:00Z", "total": None},
        {"id": "4", "negocio_id": "t1", "fecha": "2024-02-03T13:00:00Z", "total": ""},
    ]

    monkeypatch.setattr(
        FeatureEngineer,
        "get_sales_rows",
        lambda self, tenant_id, timerange=None: rows,
    )

    fe = FeatureEngineer()
    ts = fe.sales_timeseries_daily("t1", days=3)

    # We expect days: 2024-02-01, 2024-02-02, 2024-02-03
    ds_str = [str(d) for d in cast(list, ts["ds"].astype(str).tolist())]
    assert ds_str == ["2024-02-01", "2024-02-02", "2024-02-03"], ds_str
    # Totals should aggregate to 3.5 + 1.5 = 5.0 on 2024-02-01, 0.0 on 02, 0.0 on 03 (None/"" -> 0)
    ys = [float(v) for v in ts["y"].tolist()]
    assert ys == [5.0, 0.0, 0.0]
