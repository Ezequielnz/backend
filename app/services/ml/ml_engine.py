from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import cast, Callable

import numpy as np
from numpy.typing import NDArray
import pandas as pd
from prophet import Prophet
from sklearn.ensemble import IsolationForest

logger = logging.getLogger(__name__)


@dataclass
class ForecastResult:
    model: Prophet
    forecast: pd.DataFrame


class BusinessMLEngine:
    """
    Provides ML algorithms used by the ERP backend.
    - Sales forecasting with Prophet
    - Anomaly detection with Isolation Forest
    """

    # -----------------------------
    # Prophet forecasting
    # -----------------------------
    def train_sales_forecasting(self, daily_ts: pd.DataFrame) -> Prophet:
        """
        Train Prophet model on a daily time series with columns [ds, y].
        Returns trained Prophet model.
        """
        if daily_ts.empty:
            raise ValueError("Empty time series for training")
        df = daily_ts.copy()
        # Typed wrapper around pandas.to_datetime to avoid stub overload issues
        to_dt_any: Callable[..., object] = cast(Callable[..., object], getattr(pd, "to_datetime"))
        df.loc[:, "ds"] = cast(pd.Series, to_dt_any(df["ds"]))  # ensure datetime
        # Prophet's constructor stubs can be overly strict (expect str for seasonality args).
        # Call via a generic callable to avoid false-positive type errors while preserving runtime behavior.
        prophet_ctor: Callable[..., object] = cast(Callable[..., object], Prophet)
        model = cast(
            Prophet,
            prophet_ctor(
                daily_seasonality=True,
                weekly_seasonality=True,
                yearly_seasonality=True,
                seasonality_mode="additive",
            ),
        )
        fit_any: Callable[..., object] = cast(Callable[..., object], getattr(model, "fit"))
        _ = fit_any(df[["ds", "y"]])
        return model

    def forecast_sales(self, model: Prophet, horizon_days: int = 14) -> pd.DataFrame:
        mfd_any: Callable[..., object] = cast(Callable[..., object], getattr(model, "make_future_dataframe"))
        future = cast(pd.DataFrame, mfd_any(periods=horizon_days, freq="D", include_history=False))
        predict_any: Callable[..., object] = cast(Callable[..., object], getattr(model, "predict"))
        forecast = cast(pd.DataFrame, predict_any(future))
        # Keep relevant cols
        cols = ["ds", "yhat", "yhat_lower", "yhat_upper"]
        return cast(pd.DataFrame, forecast.loc[:, cols])

    # -----------------------------
    # Isolation Forest anomalies
    # -----------------------------
    def train_anomaly_detection(
        self, daily_ts: pd.DataFrame, contamination: float = 0.05, random_state: int = 42
    ) -> IsolationForest:
        if daily_ts.empty:
            raise ValueError("Empty time series for training anomalies")
        X = np.asarray(daily_ts["y"], dtype=float).reshape(-1, 1)
        # sklearn's type stubs can mark `contamination` as str-only (e.g., "auto"),
        # but at runtime it also accepts float values. Call via a generic callable
        # and cast back to avoid false-positive type errors while preserving behavior.
        iso_ctor: Callable[..., object] = cast(Callable[..., object], IsolationForest)
        model = cast(
            IsolationForest,
            iso_ctor(contamination=contamination, random_state=random_state),
        )
        fit_any2: Callable[..., object] = cast(Callable[..., object], getattr(model, "fit"))
        _ = fit_any2(X)
        return model

    def detect_anomalies(self, model: IsolationForest, daily_ts: pd.DataFrame) -> pd.DataFrame:
        if daily_ts.empty:
            return pd.DataFrame(
                {
                    "ds": pd.Series(dtype="datetime64[ns]"),
                    "y": pd.Series(dtype=float),
                    "is_anomaly": pd.Series(dtype=bool),
                    "score": pd.Series(dtype=float),
                }
            )
        X = np.asarray(daily_ts["y"], dtype=float).reshape(-1, 1)
        predict_any2: Callable[..., object] = cast(Callable[..., object], getattr(model, "predict"))
        preds: NDArray[np.int64] = cast(NDArray[np.int64], predict_any2(X))  # -1 anomaly, 1 normal
        decision_fn_any: Callable[..., object] = cast(Callable[..., object], getattr(model, "decision_function"))
        scores: NDArray[np.float64] = cast(NDArray[np.float64], decision_fn_any(X))
        out = daily_ts.copy()
        out["is_anomaly"] = (preds == -1)
        out["score"] = scores
        return cast(pd.DataFrame, out.loc[:, ["ds", "y", "is_anomaly", "score"]])
