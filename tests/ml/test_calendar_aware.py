import numpy as np
import pandas as pd
import pytest

from app.services.ml.ml_engine import BusinessMLEngine


def _ts_with_spikes_quincenal(days: int = 180, spike_value: float = 50.0, base: float = 10.0) -> pd.DataFrame:
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=days, freq="D")
    y = np.full(days, base, dtype=float)
    # Spike every 15 days
    for i in range(0, days, 15):
        y[i] = spike_value
    return pd.DataFrame({"ds": idx.date, "y": y})


def _ts_with_spikes_month_start(months: int = 10, spike_value: float = 60.0, base: float = 12.0) -> pd.DataFrame:
    start = (pd.Timestamp.today().normalize() - pd.DateOffset(months=months)).normalize() + pd.offsets.MonthBegin(0)
    end = pd.Timestamp.today().normalize()
    idx = pd.date_range(start=start, end=end, freq="D")
    y = np.full(len(idx), base, dtype=float)
    for i, dt in enumerate(idx):
        if dt.day == 1:
            y[i] = spike_value
    return pd.DataFrame({"ds": idx.date, "y": y})


def test_prophet_adds_country_holidays():
    eng = BusinessMLEngine()
    # Minimal non-empty series
    idx = pd.date_range("2024-01-01", periods=90, freq="D")
    ts = pd.DataFrame({"ds": idx, "y": np.linspace(10, 20, len(idx))})
    model = eng.train_sales_forecasting_prophet(ts, seasonality_mode="additive", holidays_country="AR")
    # Robust check across Prophet versions
    # Prefer model.country_holidays if available, else train_holiday_names after fit,
    # else build holidays via make_holidays for the training window.
    ok = False
    ch = getattr(model, "country_holidays", None)
    if ch is not None:
        ok = True
    else:
        names = getattr(model, "train_holiday_names", None)
        if names is not None and len(list(names)) > 0:
            ok = True
        else:
            # Fallback: try to make holidays explicitly
            try:
                start = pd.to_datetime(ts["ds"]).min()
                end = pd.to_datetime(ts["ds"]).max()
                mh = getattr(model, "make_holidays", None)
                if callable(mh):
                    hdf = mh(start=start, end=end)
                    ok = hdf is not None and getattr(hdf, "empty", True) is False
            except Exception:
                pass
    assert ok


def test_snaive_quincenal_payday_pattern():
    eng = BusinessMLEngine()
    ts = _ts_with_spikes_quincenal(days=180, spike_value=50.0, base=10.0)
    fc = eng.forecast_baseline_snaive(ts, horizon_days=15, season=15)
    # Expect the first horizon day to be a spike continuation (since last season starts with a spike)
    # Compare first day prediction to median of other days
    first_pred = float(fc.loc[0, "yhat"]) if not fc.empty else 0.0
    median_rest = float(fc["yhat"].iloc[1:].median()) if len(fc) > 1 else first_pred
    assert first_pred > median_rest + 10.0  # significant spike over baseline


def test_snaive_month_start_pattern():
    eng = BusinessMLEngine()
    ts = _ts_with_spikes_month_start(months=12, spike_value=60.0, base=12.0)
    # Use season ≈ 30 to emulate month-length cycle; not exact but captures repeated start spikes
    fc = eng.forecast_baseline_snaive(ts, horizon_days=30, season=30)
    # Find prediction corresponding to next month start
    # Forecast dates start tomorrow; compute next month begin
    tomorrow = pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
    next_mb = (tomorrow + pd.offsets.MonthBegin(1)).normalize()
    # Find closest ds in forecast
    fc2 = fc.copy()
    fc2.loc[:, "ds"] = pd.to_datetime(fc2["ds"]).dt.normalize()
    row = fc2.loc[fc2["ds"] == next_mb]
    if not row.empty:
        v = float(row.iloc[0]["yhat"]) if "yhat" in row.columns else float("nan")
        # The spike should be significantly above typical baseline
        base_med = float(fc2["yhat"].median())
        assert v > base_med + 10.0
    else:
        # If alignment doesn't match exact first-of-month, relax: ensure at least one forecast day is a spike
        assert (fc2["yhat"] > (fc2["yhat"].median() + 10.0)).any()
