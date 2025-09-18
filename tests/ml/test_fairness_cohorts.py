import numpy as np
import pandas as pd

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


def _make_ts(n: int, mu: float, sigma: float, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=n, freq="D")
    t = np.arange(n)
    weekly = 5.0 * np.sin(2 * np.pi * (t % 7) / 7.0)
    y = mu + weekly + rng.normal(0.0, sigma, size=n)
    return pd.DataFrame({"ds": idx, "y": y.astype(float)})


def _rolling_smape(ts: pd.DataFrame, horizon: int = 14, windows: int = 60) -> float:
    eng = BusinessMLEngine()
    n = len(ts)
    starts = list(range(max(20, n - windows - horizon), n - horizon))
    vals: list[float] = []
    for s in starts[:windows]:
        hist = ts.iloc[: s + 1]
        hold = ts.iloc[s + 1 : s + 1 + horizon]
        fc = eng.forecast_baseline_snaive(hist, horizon_days=horizon, season=7)
        if fc.empty or hold.empty:
            continue
        fc2 = fc.copy()
        fc2.loc[:, "date"] = pd.to_datetime(fc2["ds"]).dt.date.astype(str)
        hold2 = hold.copy()
        hold2.loc[:, "date"] = pd.to_datetime(hold2["ds"]).dt.date.astype(str)
        merged = hold2.merge(fc2, on="date", how="inner")
        if merged.empty:
            continue
        y = merged["y"].to_numpy(dtype=float)
        yhat = merged["yhat"].to_numpy(dtype=float)
        denom = np.abs(y) + np.abs(yhat) + 1e-6
        smape = np.mean(2.0 * np.abs(y - yhat) / denom)
        vals.append(float(smape))
    return float(np.nanmean(vals)) if vals else float("nan")


def test_fairness_cohorts_smape_gap_within_tolerance():
    # Cohortes con distribución similar (misma sigma y estructura semanal)
    A = _make_ts(n=240, mu=100.0, sigma=3.0, seed=100)
    B = _make_ts(n=200, mu=100.0, sigma=3.0, seed=101)
    smape_A = _rolling_smape(A, horizon=14, windows=60)
    smape_B = _rolling_smape(B, horizon=14, windows=60)
    assert np.isfinite(smape_A) and np.isfinite(smape_B)
    gap = abs(smape_A - smape_B)
    # Tolerancia de disparidad
    assert gap <= 0.05, f"sMAPE gap too large between cohorts: {gap:.3f} (A={smape_A:.3f}, B={smape_B:.3f})"
