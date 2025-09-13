import numpy as np
import pandas as pd
from app.services.ml.ml_engine import BusinessMLEngine


def _make_weekly_series(n: int = 90, seed: int = 123) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.date_range(start=pd.Timestamp.today().normalize() - pd.Timedelta(days=n - 1), periods=n, freq="D")
    t = np.arange(n)
    seasonal = 10.0 * np.sin(2 * np.pi * (t % 7) / 7.0)
    noise = rng.normal(0.0, 1.5, size=n)
    y = 100.0 + seasonal + noise
    return pd.DataFrame({"ds": days, "y": y})


def test_detect_anomalies_stl_flags_outlier_block():
    eng = BusinessMLEngine()
    base = _make_weekly_series(90, seed=2025)
    # Inject an outlier block around days 40-45
    idxs = list(range(40, 46))
    y2 = base["y"].to_numpy(dtype=float)
    y2[idxs] = y2[idxs] + 8.0  # strong positive deviation
    base2 = base.copy()
    base2.loc[:, "y"] = y2

    an = eng.detect_anomalies_stl(base2, period=7, z_thresh=2.5)
    # Expect some anomalies in injected block
    flagged = an.iloc[idxs]["is_anomaly"].to_numpy(dtype=bool)
    assert flagged.mean() > 0.4, "Expected at least ~40% anomalies within injected block"
    # Overall anomalies should be present but not explode
    assert an["is_anomaly"].mean() < 0.5
