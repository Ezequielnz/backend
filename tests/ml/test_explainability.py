import numpy as np
import pandas as pd
import importlib.util as _importlib_util
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


@pytest.mark.skipif(_importlib_util.find_spec("xgboost") is None, reason="xgboost not installed")
def test_xgb_feature_importances_stability():
    eng = BusinessMLEngine()

    def _make_ts(n: int = 220, mu: float = 100.0, sigma: float = 2.5, seed: int = 77) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=n, freq="D")
        t = np.arange(n)
        weekly = 5.0 * np.sin(2 * np.pi * (t % 7) / 7.0)
        y = mu + 0.1 * t + weekly + rng.normal(0.0, sigma, size=n)
        return pd.DataFrame({"ds": idx, "y": y.astype(float)})

    ts1 = _make_ts(seed=123)
    ts2 = _make_ts(seed=124)  # pequeña perturbación

    model1 = eng.train_xgboost(ts1)
    model2 = eng.train_xgboost(ts2)

    # Obtener importancias: preferir feature_importances_, fallback a booster get_score
    def _rank(model) -> list[str]:
        names = ["dow", "dom", "month", "lag_1", "lag_7"]
        fi = getattr(model, "feature_importances_", None)
        if fi is not None and np.asarray(fi).size == len(names):
            vals = np.asarray(fi).astype(float)
            order = list(np.argsort(vals)[::-1])
            return [names[i] for i in order]
        booster = getattr(model, "get_booster", None)
        if booster is not None:
            bst = booster()
            sc = bst.get_score(importance_type="weight")
            # map to names order
            vals = [float(sc.get(n, 0.0)) for n in names]
            order = list(np.argsort(np.asarray(vals))[::-1])
            return [names[i] for i in order]
        # último recurso: todas iguales
        return names

    r1 = _rank(model1)
    r2 = _rank(model2)

    # Criterio de estabilidad: al menos una de las dos primeras features coinciden entre runs
    top2_1 = set(r1[:2])
    top2_2 = set(r2[:2])
    assert len(top2_1.intersection(top2_2)) >= 1, f"Top-2 drifted excessively: {r1[:2]} vs {r2[:2]}"
