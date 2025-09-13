import numpy as np
import pandas as pd

from app.services.ml.ml_engine import BusinessMLEngine


def _gaussian_series(n: int = 300, mu: float = 100.0, sigma: float = 5.0, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=n, freq="D")
    y = rng.normal(mu, sigma, size=n)
    return pd.DataFrame({"ds": idx.date, "y": y.astype(float)})


def _rolling_naive_windows(ts: pd.DataFrame, horizon: int = 14, windows: int = 100) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    eng = BusinessMLEngine()
    y_true_all = []
    yhat_all = []
    width_all = []
    n = len(ts)
    # Start windows near the end to ensure we have horizon ahead
    starts = list(range(max(10, n - windows - horizon), n - horizon))
    for s in starts[:windows]:
        hist = ts.iloc[: s + 1]
        hold = ts.iloc[s + 1 : s + 1 + horizon]
        fc = eng.forecast_baseline_naive(hist, horizon_days=horizon)
        if fc.empty or hold.empty:
            continue
        # Align by ds
        fc2 = fc.copy()
        fc2.loc[:, "ds"] = pd.to_datetime(fc2["ds"]).dt.normalize()
        hold2 = hold.copy()
        hold2.loc[:, "ds"] = pd.to_datetime(hold2["ds"]).dt.normalize()
        merged = hold2.merge(fc2, on="ds", how="inner")
        if merged.empty:
            continue
        y_true_all.append(np.asarray(merged["y"], dtype=float))
        yhat_all.append(np.asarray(merged["yhat"], dtype=float))
        width_all.append(np.asarray(merged["yhat_upper"] - merged["yhat_lower"], dtype=float))
    if not y_true_all:
        return np.array([]), np.array([]), np.array([])
    return np.concatenate(y_true_all), np.concatenate(yhat_all), np.concatenate(width_all)


def test_pit_uniformity_baseline_naive():
    ts = _gaussian_series(n=240, mu=100.0, sigma=5.0, seed=777)
    y_true, yhat, width = _rolling_naive_windows(ts, horizon=14, windows=60)
    assert y_true.size > 0
    # Approximate sigma from interval width (80% CI => ~1.28*sigma)
    sigma_est = width / (2.0 * 1.28)
    z = (y_true - yhat) / np.clip(sigma_est, 1e-6, None)
    # PIT via standard normal CDF approximation
    from math import erf, sqrt
    pit = 0.5 * (1.0 + erf(z / sqrt(2.0)))
    # Check mean near 0.5 and central quantiles near uniform
    m = float(np.nanmean(pit))
    q10, q90 = np.nanquantile(pit, [0.1, 0.9])
    assert 0.45 <= m <= 0.55, f"PIT mean {m:.3f} not ~0.5"
    assert 0.05 <= q10 <= 0.15 and 0.85 <= q90 <= 0.95, f"PIT quantiles off: q10={q10:.3f}, q90={q90:.3f}"


def test_coverage_by_horizon_baseline_naive():
    ts = _gaussian_series(n=240, mu=80.0, sigma=6.0, seed=101)
    eng = BusinessMLEngine()
    n = len(ts)
    horizon = 10
    cover = []
    for s in range(n - 50, n - horizon):
        hist = ts.iloc[: s + 1]
        hold = ts.iloc[s + 1 : s + 1 + horizon]
        fc = eng.forecast_baseline_naive(hist, horizon_days=horizon)
        if fc.empty:
            continue
        fc2 = fc.copy()
        fc2.loc[:, "ds"] = pd.to_datetime(fc2["ds"]).dt.normalize()
        hold2 = hold.copy()
        hold2.loc[:, "ds"] = pd.to_datetime(hold2["ds"]).dt.normalize()
        merged = hold2.merge(fc2, on="ds", how="inner")
        inside = (merged["y"] >= merged["yhat_lower"]) & (merged["y"] <= merged["yhat_upper"])
        cover.append(inside.to_numpy(dtype=float))
    cov_arr = np.array(cover)
    assert cov_arr.size > 0
    # Coverage per horizon (mean across windows)
    cov_per_h = cov_arr.mean(axis=0)
    # Expectation near 0.8 with generous tolerance
    assert np.all((cov_per_h >= 0.65) & (cov_per_h <= 0.90)), f"Coverage per horizon out of bounds: {cov_per_h}"
