import numpy as np
import pandas as pd

# Ensure app package is importable both under pytest (conftest handles sys.path)
# and when the file is opened standalone in some IDEs.
try:
    from app.services.ml.ml_engine import BusinessMLEngine
except ModuleNotFoundError:  # pragma: no cover - IDE path fallback
    import sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from app.services.ml.ml_engine import BusinessMLEngine


def _series_with_tail_volatility(days: int = 200, sigma_base: float = 2.0, sigma_tail: float = 6.0, tail_len: int = 30, seed: int = 123) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=days, freq="D")
    t = np.arange(days)
    seasonal = 5.0 * np.sin(2 * np.pi * (t % 7) / 7.0)
    y = 100.0 + 0.2 * t + seasonal + rng.normal(0.0, sigma_base, size=days)
    # Increase volatility on the tail segment
    if tail_len > 0 and tail_len < days:
        add_noise = rng.normal(0.0, sigma_tail, size=tail_len)
        y[-tail_len:] = (100.0 + 0.2 * t[-tail_len:] + seasonal[-tail_len:]) + add_noise
    return pd.DataFrame({"ds": idx, "y": y.astype(float)})


def test_intervals_widen_after_tail_volatility():
    eng = BusinessMLEngine()
    H = 14
    # Pre: stable volatility (tail sigma == base)
    pre = _series_with_tail_volatility(days=220, sigma_base=2.0, sigma_tail=2.0, tail_len=30, seed=1001)
    fc_pre = eng.forecast_baseline_naive(pre, horizon_days=H)
    width_pre = (fc_pre["yhat_upper"] - fc_pre["yhat_lower"]).to_numpy(dtype=float)
    mean_width_pre = float(np.nanmean(width_pre)) if width_pre.size else 0.0

    # Post: sudden volatility increase on tail
    post = _series_with_tail_volatility(days=220, sigma_base=2.0, sigma_tail=6.0, tail_len=30, seed=1001)
    fc_post = eng.forecast_baseline_naive(post, horizon_days=H)
    width_post = (fc_post["yhat_upper"] - fc_post["yhat_lower"]).to_numpy(dtype=float)
    mean_width_post = float(np.nanmean(width_post)) if width_post.size else 0.0

    # Expect intervals to widen meaningfully (factor >= 1.5)
    assert mean_width_post >= mean_width_pre * 1.5, f"width_post {mean_width_post:.3f} should be >= 1.5 * width_pre {mean_width_pre:.3f}"
