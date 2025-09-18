import numpy as np
import pandas as pd
import pytest

# Fallback import for IDE standalone execution
try:
    from app.services.ml.ml_engine import BusinessMLEngine
except ModuleNotFoundError:  # pragma: no cover
    import sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from app.services.ml.ml_engine import BusinessMLEngine


def _weekly_gaussian_series(n: int = 300, mu: float = 100.0, sigma: float = 3.0, seed: int = 123) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=n, freq="D")
    t = np.arange(n)
    weekly = 5.0 * np.sin(2 * np.pi * (t % 7) / 7.0)
    y = mu + weekly + rng.normal(0.0, sigma, size=n)
    return pd.DataFrame({"ds": idx, "y": y.astype(float)})


def _rolling_windows(ts: pd.DataFrame, horizon: int = 14, windows: int = 80):
    eng = BusinessMLEngine()
    y_true_all: list[np.ndarray] = []
    yhat_all: list[np.ndarray] = []
    width_all: list[np.ndarray] = []
    n = len(ts)
    starts = list(range(max(20, n - windows - horizon), n - horizon))
    for s in starts[:windows]:
        hist = ts.iloc[: s + 1]
        hold = ts.iloc[s + 1 : s + 1 + horizon]
        fc = eng.forecast_baseline_snaive(hist, horizon_days=horizon, season=7)
        if fc.empty or hold.empty:
            continue
        fc2 = fc.copy()
        # Align using date string to avoid dtype mismatches (datetime64 vs object)
        fc2.loc[:, "date"] = pd.to_datetime(fc2["ds"]).dt.date.astype(str)
        hold2 = hold.copy()
        hold2.loc[:, "date"] = pd.to_datetime(hold2["ds"]).dt.date.astype(str)
        merged = hold2.merge(fc2, on="date", how="inner")
        if merged.empty:
            continue
        y_true_all.append(np.asarray(merged["y"], dtype=float))
        yhat_all.append(np.asarray(merged["yhat"], dtype=float))
        width_all.append(np.asarray(merged["yhat_upper"] - merged["yhat_lower"], dtype=float))
    if not y_true_all:
        return np.array([]), np.array([]), np.array([])
    return np.concatenate(y_true_all), np.concatenate(yhat_all), np.concatenate(width_all)


def _pit_from_gaussian(y_true: np.ndarray, yhat: np.ndarray, width: np.ndarray) -> np.ndarray:
    # For 80% intervals, half-width ~ 1.28 * sigma => sigma ~ width / (2 * 1.28)
    sigma_est = width / (2.0 * 1.28)
    z = (y_true - yhat) / np.clip(sigma_est, 1e-6, None)
    from math import erf, sqrt
    pit = 0.5 * (1.0 + erf(z / sqrt(2.0)))
    return pit


def test_pit_uniformity_snaive_weekly():
    ts = _weekly_gaussian_series(n=260, mu=80.0, sigma=3.0, seed=2024)
    y_true, yhat, width = _rolling_windows(ts, horizon=14, windows=60)
    assert y_true.size > 0
    pit = _pit_from_gaussian(y_true, yhat, width)
    m = float(np.nanmean(pit))
    q10, q90 = np.nanquantile(pit, [0.1, 0.9])
    # Tolerancias de uniformidad amplias
    assert 0.45 <= m <= 0.55, f"PIT mean {m:.3f} not ~0.5"
    assert 0.05 <= q10 <= 0.15 and 0.85 <= q90 <= 0.95, f"PIT quantiles off: q10={q10:.3f}, q90={q90:.3f}"


def test_sharpness_vs_reliability_tradeoff():
    ts_lo = _weekly_gaussian_series(n=260, mu=100.0, sigma=2.0, seed=7)
    ts_hi = _weekly_gaussian_series(n=260, mu=100.0, sigma=5.0, seed=7)
    y_true_lo, yhat_lo, width_lo = _rolling_windows(ts_lo, horizon=10, windows=50)
    y_true_hi, yhat_hi, width_hi = _rolling_windows(ts_hi, horizon=10, windows=50)
    assert y_true_lo.size > 0 and y_true_hi.size > 0
    # Sharpness: anchos en sigma alta deben ser mayores
    mw_lo = float(np.nanmean(width_lo))
    mw_hi = float(np.nanmean(width_hi))
    assert mw_hi >= mw_lo * 1.3
    # Reliability aproximada: cobertura dentro de [0.6, 0.95] en ambos
    def _coverage(y_true, yhat, width):
        sigma_est = width / (2.0 * 1.28)
        from math import erf, sqrt
        pit = 0.5 * (1.0 + erf(((y_true - yhat) / np.clip(sigma_est, 1e-6, None)) / sqrt(2.0)))
        return float(np.nanmean((pit >= 0.1) & (pit <= 0.9)))
    cov_lo = _coverage(y_true_lo, yhat_lo, width_lo)
    cov_hi = _coverage(y_true_hi, yhat_hi, width_hi)
    assert 0.60 <= cov_lo <= 0.95
    assert 0.60 <= cov_hi <= 0.95
