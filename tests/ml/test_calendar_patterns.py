import numpy as np
import pandas as pd
import types
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


def _sales_only_month_start(months: int = 12, base: float = 0.0, spike: float = 50.0) -> pd.DataFrame:
    start = (pd.Timestamp.today().normalize() - pd.DateOffset(months=months)).normalize() + pd.offsets.MonthBegin(0)
    end = pd.Timestamp.today().normalize()
    idx = pd.date_range(start=start, end=end, freq="D")
    y = np.full(len(idx), base, dtype=float)
    for i, dt in enumerate(idx):
        if 1 <= dt.day <= 3:
            y[i] = spike
    return pd.DataFrame({"ds": idx, "y": y.astype(float)})


def test_calendar_pattern_pipeline_snaive(monkeypatch):
    fake = FakeSupabase()
    import app.services.ml.pipeline as pipe_mod
    import app.services.ml.model_version_manager as mvm_mod
    import app.db.supabase_client as sc_mod
    import app.services.ml.feature_engineer as fe_mod

    monkeypatch.setattr(pipe_mod, "get_supabase_service_client", lambda: fake)
    monkeypatch.setattr(mvm_mod, "get_supabase_service_client", lambda: fake)
    monkeypatch.setattr(sc_mod, "get_supabase_service_client", lambda: fake)

    # Force candidates to snaive to capture monthly start pattern
    monkeypatch.setattr(pipe_mod.ml_settings.__class__, "get_tenant_overrides", lambda self, tenant_id: {
        "ML_MODEL_CANDIDATES": "snaive",
        "ML_SELECT_BEST": True,
        "ML_CV_FOLDS": 2,
        # Ensure SNaive season approximates a month
        "ML_STL_PERIOD": 30,
    })

    series = _sales_only_month_start(months=10, base=0.0, spike=60.0)
    monkeypatch.setattr(fe_mod.FeatureEngineer, "sales_timeseries_daily", lambda self, bid, days=365: series)

    # Use a longer horizon to guarantee the next month start is within the window
    H = 35
    res = pl.train_and_predict_sales(
        business_id="tenant-cal",
        horizon_days=H,
        history_days=len(series),
        include_anomaly=False,
        cv_folds=2,
    )
    assert isinstance(res, dict) and res.get("trained") is True

    rows = [r for r in fake.store.get("ml_predictions", []) if r.get("prediction_type") == "sales_forecast"]
    last = rows[-H:]
    assert len(last) == H

    # Build arrays for analysis
    df_fc = pd.DataFrame(last)
    df_fc.loc[:, "date"] = pd.to_datetime(df_fc["prediction_date"]).dt.normalize()
    yhat = df_fc["predicted_values"].apply(lambda d: float(cast(dict, d).get("yhat", np.nan))).to_numpy(dtype=float)
    ylo = df_fc["predicted_values"].apply(lambda d: float(cast(dict, d).get("yhat_lower", np.nan))).to_numpy(dtype=float)
    yhi = df_fc["predicted_values"].apply(lambda d: float(cast(dict, d).get("yhat_upper", np.nan))).to_numpy(dtype=float)

    # Identify positions for next month start and days 1-3 within horizon
    tomorrow = pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
    month_begin = (tomorrow + pd.offsets.MonthBegin(1)).normalize()
    idxs_1_3 = []
    for i in range(H):
        di = tomorrow + pd.Timedelta(days=i)
        if di.day in (1, 2, 3) and di >= month_begin and di < (month_begin + pd.Timedelta(days=7)):
            idxs_1_3.append(i)
    idxs_rest = [i for i in range(H) if i not in idxs_1_3]

    # Expect higher predictions on days 1-3 and near-zero elsewhere
    med_spike = float(np.nanmedian(yhat[idxs_1_3])) if idxs_1_3 else 0.0
    med_rest = float(np.nanmedian(yhat[idxs_rest])) if idxs_rest else 0.0
    assert med_spike > med_rest + 10.0

    # Uncertainty: con SNaive el ancho es constante por construcción.
    # Validamos que fuera de 1–3 no sea menor (tolerancia 10%).
    width_in = float(np.nanmedian(yhi[idxs_1_3] - ylo[idxs_1_3])) if idxs_1_3 else 0.0
    width_out = float(np.nanmedian(yhi[idxs_rest] - ylo[idxs_rest])) if idxs_rest else 0.0
    assert width_out >= width_in * 0.9
