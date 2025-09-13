import pandas as pd
import numpy as np
from app.services.ml.ml_engine import BusinessMLEngine


def test_make_time_features_basic():
    eng = BusinessMLEngine()
    ds = pd.to_datetime(pd.Series([
        "2024-01-01",  # Tue (dayofweek=1 if Monday=0)
        "2024-02-15",
        "2024-12-31",
    ]))
    feats = eng._make_time_features(ds)
    assert list(feats.columns) == ["dow", "dom", "month"]
    assert feats.shape[0] == 3
    # Basic bounds
    assert feats["dow"].between(0, 6).all()
    assert feats["dom"].between(1, 31).all()
    assert feats["month"].between(1, 12).all()


def test_add_lags_shift_values():
    eng = BusinessMLEngine()
    y = pd.Series([1.0, 2.0, 3.0, 4.0])
    lags = eng._add_lags(y, [1, 2])
    assert list(lags.columns) == ["lag_1", "lag_2"]
    # lag_1 at idx 2 should be previous value 2.0; lag_2 at idx 3 should be 2.0
    assert np.isnan(lags.loc[0, "lag_1"]) and np.isnan(lags.loc[0, "lag_2"])
    assert lags.loc[2, "lag_1"] == 2.0
    assert lags.loc[3, "lag_2"] == 2.0
