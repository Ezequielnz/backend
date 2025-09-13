import numpy as np
import pandas as pd

from app.services.ml.ml_engine import BusinessMLEngine


def _ar1_series(n: int = 240, phi: float = 0.5, sigma: float = 1.0, seed: int = 2025) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    eps = rng.normal(0.0, sigma, size=n + 30)  # extra for future holdout
    y = np.zeros(n + 30, dtype=float)
    for t in range(1, n + 30):
        y[t] = phi * y[t - 1] + eps[t]
    ds = pd.date_range(start=pd.Timestamp.today().normalize() - pd.Timedelta(days=n - 1), periods=n, freq="D")
    train = pd.DataFrame({"ds": ds, "y": y[:n]})
    holdout = pd.DataFrame({
        "ds": pd.date_range(start=ds[-1] + pd.Timedelta(days=1), periods=30, freq="D"),
        "y": y[n : n + 30],
    })
    return train, holdout


def test_interval_coverage_sarimax_approx_80():
    eng = BusinessMLEngine()
    train, holdout = _ar1_series(n=240, phi=0.6, sigma=1.0, seed=7)
    fit_res = eng.train_sarimax(train, order=(1, 0, 0), seasonal_order=None)
    fc = eng.forecast_sales_sarimax(fit_res, horizon_days=len(holdout))
    # Align by ds
    fc = fc.copy()
    fc["ds"] = pd.to_datetime(fc["ds"]).dt.normalize()
    merged = pd.merge(holdout, fc, on="ds", how="inner")
    assert len(merged) == len(holdout)
    inside = (merged["y"] >= merged["yhat_lower"]) & (merged["y"] <= merged["yhat_upper"])
    coverage = float(inside.mean())
    # Allow generous tolerance due to model estimation variance
    assert 0.65 <= coverage <= 0.90, f"Coverage {coverage:.3f} outside expected 80%±15%"
