import numpy as np
import pandas as pd

# Ensure app package import works both under pytest and when opened standalone in IDEs
try:
    from app.services.ml.ml_engine import BusinessMLEngine
except ModuleNotFoundError:  # pragma: no cover - IDE path fallback
    import sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from app.services.ml.ml_engine import BusinessMLEngine


def _stable_series(days: int = 200, sigma: float = 2.0, seed: int = 2025) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=days, freq="D")
    t = np.arange(days)
    seasonal = 5.0 * np.sin(2 * np.pi * (t % 7) / 7.0)
    y = 100.0 + 0.2 * t + seasonal + rng.normal(0.0, sigma, size=days)
    return pd.DataFrame({"ds": idx, "y": y.astype(float)})


def _with_missing_blocks_as_zeros(df: pd.DataFrame, block_len: int = 28, step: int = 2) -> pd.DataFrame:
    """Simula bloque de faltantes en el tramo final, representados como ceros.
    Esto incrementa la varianza reciente para que los PIs del baseline se ensanchen.
    """
    df2 = df.copy()
    n = len(df2)
    start = max(0, n - block_len)
    # Set every `step` day in the tail block to zero
    y = df2["y"].to_numpy(dtype=float)
    y[start:n:step] = 0.0
    df2.loc[:, "y"] = y
    return df2


def test_missing_blocks_increase_uncertainty_naive():
    eng = BusinessMLEngine()
    H = 14

    base = _stable_series(days=220, sigma=2.0, seed=777)
    fc_base = eng.forecast_baseline_naive(base, horizon_days=H)
    w_base = (fc_base["yhat_upper"] - fc_base["yhat_lower"]).to_numpy(dtype=float)
    mean_w_base = float(np.nanmean(w_base)) if w_base.size else 0.0

    miss = _with_missing_blocks_as_zeros(base, block_len=28, step=2)
    fc_miss = eng.forecast_baseline_naive(miss, horizon_days=H)

    # Validaciones de salida
    assert not fc_miss.empty and len(fc_miss) == H
    assert np.isfinite(fc_miss[["yhat", "yhat_lower", "yhat_upper"]].to_numpy(dtype=float)).all()
    assert (fc_miss["yhat_lower"] <= fc_miss["yhat"]).all() and (fc_miss["yhat"] <= fc_miss["yhat_upper"]).all()

    w_miss = (fc_miss["yhat_upper"] - fc_miss["yhat_lower"]).to_numpy(dtype=float)
    mean_w_miss = float(np.nanmean(w_miss)) if w_miss.size else 0.0

    # Criterio: incertidumbre (ancho de PI) aumenta de forma significativa (>= 1.5x)
    assert mean_w_miss >= mean_w_base * 1.5, f"width_miss {mean_w_miss:.3f} should be >= 1.5 * width_base {mean_w_base:.3f}"
