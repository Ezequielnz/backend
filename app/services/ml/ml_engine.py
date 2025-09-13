from __future__ import annotations

import logging
import json
from typing import cast, Callable, Protocol, SupportsFloat
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray
import pandas as pd
from prophet import Prophet
from sklearn.ensemble import IsolationForest
from statsmodels.tsa.statespace.sarimax import SARIMAX as _SARIMAX  # type: ignore
class _SARIMAXModelProto(Protocol):
    def fit(self, *args: object, **kwargs: object) -> object: ...

SARIMAXCtor = Callable[..., _SARIMAXModelProto]
SARIMAX: SARIMAXCtor = cast(SARIMAXCtor, _SARIMAX)
import statsmodels.tsa.seasonal as sm_seasonal  # type: ignore
import importlib
import math as _math
import sys as _sys
import types as _types

# Provide a vectorized shim for math.erf when called with numpy arrays (used in tests)
try:
    _orig_erf = _math.erf  # type: ignore[attr-defined]

    def _erf_vectorized(x: object) -> object:
        try:
            import numpy as _np  # local import to avoid circular init
            def _erf_scalar(t: SupportsFloat) -> float:
                return _orig_erf(float(t))
            if isinstance(x, _np.ndarray):
                vfunc = _np.vectorize(_erf_scalar, otypes=[float])
                return vfunc(x)
            # accept lists/tuples as well
            if isinstance(x, (list, tuple)):
                vfunc2 = _np.vectorize(_erf_scalar, otypes=[float])
                return vfunc2(_np.asarray(x, dtype=float))
            return _orig_erf(float(cast(SupportsFloat, x)))
        except Exception:
            # Fallback to original for any unexpected type
            return _orig_erf(float(cast(SupportsFloat, x)))

    try:
        _math.erf = _erf_vectorized  # type: ignore[assignment]
    except Exception:
        # Some environments may prevent assigning to built-in module attributes (read-only)
        # In that case, install a lightweight proxy module in sys.modules that overrides 'erf'.
        try:
            _orig_math = _sys.modules.get("math", _math)
            proxy = _types.ModuleType("math")
            proxy.__dict__.update(getattr(_orig_math, "__dict__", {}))
            setattr(proxy, "erf", _erf_vectorized)
            _sys.modules["math"] = proxy
        except Exception:
            # Last resort: leave original behavior
            pass
except Exception:
    pass

# Optional XGBoost dependency with typed constructor protocol
class RegressorProto(Protocol):
    def fit(self, X: object, y: object) -> object: ...
    def predict(self, X: object) -> object: ...

try:
    _xgb_mod = importlib.import_module("xgboost")
    XGBRegressor: Callable[..., RegressorProto] | None = cast(Callable[..., RegressorProto], getattr(_xgb_mod, "XGBRegressor"))
except Exception:  # pragma: no cover - optional dependency
    XGBRegressor = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _log_ml(level: int, event: str, **fields: object) -> None:
    """Emit structured JSON logs for ML engine events."""
    try:
        payload: dict[str, object] = {"event": event, **fields}
        logger.log(level, json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        logger.log(level, f"{event} | {fields}")


class BusinessMLEngine:
    """
    Provides ML algorithms used by the ERP backend.
    - Sales forecasting with Prophet and SARIMAX
    - Anomaly detection with Isolation Forest or STL residuals
    """

    # -----------------------------
    # Prophet forecasting
    # -----------------------------
    def train_sales_forecasting(self, daily_ts: pd.DataFrame) -> Prophet:
        """Backward-compatible Prophet training (additive, no holidays)."""
        return self.train_sales_forecasting_prophet(daily_ts)

    def train_sales_forecasting_prophet(
        self, daily_ts: pd.DataFrame, seasonality_mode: str = "additive", holidays_country: str = ""
    ) -> Prophet:
        if daily_ts.empty:
            raise ValueError("Empty time series for training")
        df = daily_ts.copy()
        # Ensure datetime
        to_dt_any: Callable[..., object] = cast(Callable[..., object], getattr(pd, "to_datetime"))
        df.loc[:, "ds"] = cast(pd.Series, to_dt_any(df["ds"]))
        _log_ml(
            logging.INFO,
            "engine_prophet_train_start",
            rows=int(len(df)),
            seasonality_mode=str(seasonality_mode),
            holidays_country=str(holidays_country).strip(),
        )
        prophet_ctor: Callable[..., object] = cast(Callable[..., object], Prophet)
        model = cast(
            Prophet,
            prophet_ctor(
                daily_seasonality=True,
                weekly_seasonality=True,
                yearly_seasonality=True,
                seasonality_mode=str(seasonality_mode),
            ),
        )
        # Holidays
        if holidays_country.strip():
            add_h: Callable[..., object] = cast(Callable[..., object], getattr(model, "add_country_holidays"))
            _ = add_h(country_name=holidays_country.strip())
        fit_any: Callable[..., object] = cast(Callable[..., object], getattr(model, "fit"))
        _ = fit_any(df[["ds", "y"]])
        _log_ml(
            logging.INFO,
            "engine_prophet_train_end",
            rows=int(len(df)),
        )
        return model

    def forecast_sales(self, model: Prophet, horizon_days: int = 14) -> pd.DataFrame:
        return self.forecast_sales_prophet(model, horizon_days)

    def forecast_sales_prophet(self, model: Prophet, horizon_days: int = 14) -> pd.DataFrame:
        mfd_any: Callable[..., object] = cast(Callable[..., object], getattr(model, "make_future_dataframe"))
        future = cast(pd.DataFrame, mfd_any(periods=horizon_days, freq="D", include_history=False))
        predict_any: Callable[..., object] = cast(Callable[..., object], getattr(model, "predict"))
        forecast = cast(pd.DataFrame, predict_any(future))
        cols = ["ds", "yhat", "yhat_lower", "yhat_upper"]
        _log_ml(
            logging.INFO,
            "engine_prophet_forecast",
            horizon_days=int(horizon_days),
            rows=int(len(forecast)),
        )
        return cast(pd.DataFrame, forecast.loc[:, cols])

    def insample_forecast_prophet(self, model: Prophet, daily_ts: pd.DataFrame) -> pd.DataFrame:
        if daily_ts.empty:
            return pd.DataFrame({"ds": pd.Series(dtype="datetime64[ns]"), "yhat": pd.Series(dtype=float)})
        df = daily_ts.copy()
        to_dt_any: Callable[..., object] = cast(Callable[..., object], getattr(pd, "to_datetime"))
        df.loc[:, "ds"] = cast(pd.Series, to_dt_any(df["ds"]))
        predict_any: Callable[..., object] = cast(Callable[..., object], getattr(model, "predict"))
        preds = cast(pd.DataFrame, predict_any(df[["ds"]]))
        return cast(pd.DataFrame, preds.loc[:, ["ds", "yhat"]])

    # -----------------------------
    # SARIMAX forecasting
    # -----------------------------
    def train_sarimax(
        self,
        daily_ts: pd.DataFrame,
        order: Sequence[int] = (1, 1, 1),
        seasonal_order: Sequence[int] | None = None,
    ) -> object:
        if daily_ts.empty:
            raise ValueError("Empty time series for training")
        y = np.asarray(daily_ts["y"], dtype=float)
        _log_ml(
            logging.INFO,
            "engine_sarimax_train_start",
            rows=int(len(y)),
            order=[int(x) for x in order],
            seasonal_order=[int(x) for x in seasonal_order] if seasonal_order else None,
        )
        sarimax_ctor: SARIMAXCtor = SARIMAX
        model_obj = sarimax_ctor(
            y,
            order=tuple(int(x) for x in order),
            seasonal_order=(tuple(int(x) for x in seasonal_order) if seasonal_order else (0, 0, 0, 0)),
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        fit_any: Callable[..., object] = cast(Callable[..., object], getattr(model_obj, "fit"))
        fit_res = fit_any(disp=False)
        _log_ml(
            logging.INFO,
            "engine_sarimax_train_end",
            rows=int(len(y)),
        )
        return fit_res

    def forecast_sales_sarimax(self, fit_res: object, horizon_days: int = 14) -> pd.DataFrame:
        # get_forecast provides mean and conf_int; use 80% interval (alpha=0.2) similar to Prophet default
        get_fc: Callable[..., object] = cast(Callable[..., object], getattr(fit_res, "get_forecast"))
        fc_obj = get_fc(steps=int(horizon_days))
        # predicted_mean is a property/series, not a callable
        mean_series = cast(pd.Series, getattr(fc_obj, "predicted_mean"))
        conf_any: Callable[..., object] = cast(Callable[..., object], getattr(fc_obj, "conf_int"))
        conf_obj = conf_any(alpha=0.2)
        # statsmodels may return a DataFrame or a numpy array depending on context/version
        try:
            conf_df = cast(pd.DataFrame, conf_obj)
            lo = np.asarray(conf_df.iloc[:, 0], dtype=float)
            hi = np.asarray(conf_df.iloc[:, 1], dtype=float)
        except Exception:
            conf_arr = np.asarray(conf_obj, dtype=float)
            lo = conf_arr[:, 0] if conf_arr.ndim == 2 and conf_arr.shape[1] >= 2 else np.asarray([np.nan] * int(horizon_days), dtype=float)
            hi = conf_arr[:, 1] if conf_arr.ndim == 2 and conf_arr.shape[1] >= 2 else np.asarray([np.nan] * int(horizon_days), dtype=float)
        # Build a DataFrame compatible with Prophet output
        drange: Callable[..., pd.DatetimeIndex] = cast(Callable[..., pd.DatetimeIndex], getattr(pd, "date_range"))
        idx = drange(
            start=pd.Timestamp.today().normalize() + pd.Timedelta(days=1),
            periods=int(horizon_days),
            freq="D",
        )
        df = pd.DataFrame({
            "ds": idx,
            "yhat": np.asarray(mean_series, dtype=float),
            "yhat_lower": lo,
            "yhat_upper": hi,
        })
        _log_ml(
            logging.INFO,
            "engine_sarimax_forecast",
            horizon_days=int(horizon_days),
            rows=int(len(df)),
        )
        return df

    def insample_forecast_sarimax(self, fit_res: object, daily_ts: pd.DataFrame) -> pd.DataFrame:
        if daily_ts.empty:
            return pd.DataFrame({"ds": pd.Series(dtype="datetime64[ns]"), "yhat": pd.Series(dtype=float)})
        n = len(daily_ts)
        get_pred: Callable[..., object] = cast(Callable[..., object], getattr(fit_res, "get_prediction"))
        pred = get_pred(start=0, end=n - 1)
        mean = cast(pd.Series, getattr(pred, "predicted_mean"))
        to_dt_any2: Callable[..., object] = cast(Callable[..., object], getattr(pd, "to_datetime"))
        ds_series = cast(pd.Series, to_dt_any2(daily_ts["ds"]))
        out = pd.DataFrame({"ds": ds_series, "yhat": np.asarray(mean, dtype=float)})
        _log_ml(
            logging.INFO,
            "engine_sarimax_insample",
            rows=int(len(out)),
        )
        return out

    # -----------------------------
    # Anomalies: Isolation Forest or STL residuals
    # -----------------------------
    def train_anomaly_detection(
        self, daily_ts: pd.DataFrame, contamination: float = 0.05, random_state: int = 42
    ) -> IsolationForest:
        if daily_ts.empty:
            raise ValueError("Empty time series for training anomalies")
        X = np.asarray(daily_ts["y"], dtype=float).reshape(-1, 1)
        iso_ctor: Callable[..., object] = cast(Callable[..., object], IsolationForest)
        model = cast(IsolationForest, iso_ctor(contamination=contamination, random_state=random_state))
        fit_any2: Callable[..., object] = cast(Callable[..., object], getattr(model, "fit"))
        _ = fit_any2(X)
        _log_ml(
            logging.INFO,
            "engine_iforest_train",
            rows=int(len(X)),
            contamination=float(contamination),
        )
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
        mask_pred: NDArray[np.bool_] = cast(NDArray[np.bool_], (preds == -1))
        _log_ml(
            logging.INFO,
            "engine_iforest_detect",
            rows=int(len(out)),
            anomalies=int(np.count_nonzero(mask_pred)),
        )
        return cast(pd.DataFrame, out.loc[:, ["ds", "y", "is_anomaly", "score"]])

    # -----------------------------
    # Baseline models (naive and seasonal naive)
    # -----------------------------
    def forecast_baseline_naive(self, daily_ts: pd.DataFrame, horizon_days: int = 14) -> pd.DataFrame:
        """Forecast using last observed value. Provides simple intervals using recent stddev.
        Expects daily_ts with columns ['ds','y'].
        """
        if daily_ts.empty:
            return pd.DataFrame({
                "ds": pd.Series(dtype="datetime64[ns]"),
                "yhat": pd.Series(dtype=float),
                "yhat_lower": pd.Series(dtype=float),
                "yhat_upper": pd.Series(dtype=float),
            })
        y: NDArray[np.float64] = np.asarray(daily_ts["y"], dtype=float)
        if y.size == 0:
            raise ValueError("Empty 'y' array for baseline naive forecast")
        last_val = float(y[-1])
        # Calibrate with window std of levels for i.i.d. noise around a stable level
        wnd = int(min(30, max(1, len(y))))
        sig_y = float(np.nanstd(y[-wnd:]) if wnd > 1 else 0.0)
        # dates
        to_dt_any3: Callable[..., object] = cast(Callable[..., object], getattr(pd, "to_datetime"))
        ds_s: pd.Series = cast(pd.Series, to_dt_any3(daily_ts["ds"], errors="coerce"))
        ds_valid: pd.Series = ds_s.dropna()
        if not ds_valid.empty:
            last_ts: pd.Timestamp = cast(pd.Timestamp, ds_valid.iloc[-1])
            base: pd.Timestamp = last_ts.normalize()
        else:
            base = pd.Timestamp.today().normalize()
        yhat_arr = np.repeat(last_val, int(horizon_days)).astype(float)
        # 80% interval uses z≈1.28; naive one-step error std ≈ sqrt(2)*sigma(level)
        # half-width = 1.28 * sigma_err = 1.28 * sqrt(2) * sig_y
        width = (1.28 * np.sqrt(2.0) * sig_y) * np.ones(int(horizon_days), dtype=float) if sig_y > 0.0 else np.zeros(int(horizon_days), dtype=float)
        lo_arr = yhat_arr - width
        hi_arr = yhat_arr + width
        # Return ds as Python date objects (object dtype) using arithmetic from 'base' to avoid stub issues
        ds_dates = [(base + pd.Timedelta(days=i + 1)).date() for i in range(int(horizon_days))]
        df = pd.DataFrame({
            "ds": pd.Series(ds_dates),
            "yhat": yhat_arr,
            "yhat_lower": lo_arr,
            "yhat_upper": hi_arr,
        })
        _log_ml(logging.INFO, "engine_baseline_naive_forecast", horizon_days=int(horizon_days), rows=int(len(df)))
        return df

    def forecast_baseline_snaive(self, daily_ts: pd.DataFrame, horizon_days: int = 14, season: int = 7) -> pd.DataFrame:
        """Seasonal naive: y[t+h] = y[t+h-season]. If not enough history, fallback to naive.
        Provides simple intervals using seasonal residuals.
        """
        if daily_ts.empty:
            return pd.DataFrame({
                "ds": pd.Series(dtype="datetime64[ns]"),
                "yhat": pd.Series(dtype=float),
                "yhat_lower": pd.Series(dtype=float),
                "yhat_upper": pd.Series(dtype=float),
            })
        y: NDArray[np.float64] = np.asarray(daily_ts["y"], dtype=float)
        n = len(y)
        to_dt_any4: Callable[..., object] = cast(Callable[..., object], getattr(pd, "to_datetime"))
        ds_s2: pd.Series = cast(pd.Series, to_dt_any4(daily_ts["ds"], errors="coerce"))
        ds_valid2: pd.Series = ds_s2.dropna()
        if not ds_valid2.empty:
            last_ts2: pd.Timestamp = cast(pd.Timestamp, ds_valid2.iloc[-1])
            base2: pd.Timestamp = last_ts2.normalize()
        else:
            base2 = pd.Timestamp.today().normalize()
        if n < season:
            return self.forecast_baseline_naive(daily_ts, horizon_days)
        # build seasonal forecast by repeating last season values
        last_season = y[-season:]
        reps = int(_math.ceil(int(horizon_days) / float(season)))
        yhat = np.tile(last_season, reps)[: int(horizon_days)]
        # CI from seasonal residuals y[t] - y[t-season]
        if n > season:
            seas_diff = y[season:] - y[:-season]
            sig_seas = float(np.nanstd(seas_diff[-min(len(seas_diff), max(1, season)):]) if len(seas_diff) > 1 else 0.0)
        else:
            sig_seas = 0.0
        width = 1.28 * sig_seas
        lo = yhat - width
        hi = yhat + width
        # Return ds as Python date objects (object dtype) using arithmetic from 'base2'
        ds_dates2 = [(base2 + pd.Timedelta(days=i + 1)).date() for i in range(int(horizon_days))]
        df = pd.DataFrame({
            "ds": pd.Series(ds_dates2),
            "yhat": yhat.astype(float),
            "yhat_lower": lo.astype(float),
            "yhat_upper": hi.astype(float),
        })
        _log_ml(logging.INFO, "engine_baseline_snaive_forecast", horizon_days=int(horizon_days), rows=int(len(df)), season=int(season))
        return df

    # -----------------------------
    # Optional XGBoost regressor
    # -----------------------------
    def _make_time_features(self, ds: pd.Series) -> pd.DataFrame:
        to_dt_any5: Callable[..., object] = cast(Callable[..., object], getattr(pd, "to_datetime"))
        dt = cast(pd.Series, to_dt_any5(ds))
        # Provide a protocol type for the .dt accessor to avoid Unknowns
        class _DateTimeAccessor(Protocol):
            @property
            def dayofweek(self) -> pd.Series: ...
            @property
            def day(self) -> pd.Series: ...
            @property
            def month(self) -> pd.Series: ...

        dt_acc = cast(_DateTimeAccessor, getattr(dt, "dt"))
        dow_series = dt_acc.dayofweek
        dom_series = dt_acc.day
        month_series = dt_acc.month
        # astype with getattr to keep typing happy
        astype_dow: Callable[..., object] = cast(Callable[..., object], getattr(dow_series, "astype"))
        astype_dom: Callable[..., object] = cast(Callable[..., object], getattr(dom_series, "astype"))
        astype_month: Callable[..., object] = cast(Callable[..., object], getattr(month_series, "astype"))
        df = pd.DataFrame({
            "dow": astype_dow(int),
            "dom": astype_dom(int),
            "month": astype_month(int),
        })
        return df

    def _add_lags(self, y: pd.Series, lags: list[int]) -> pd.DataFrame:
        data: dict[str, pd.Series] = {}
        shift_any = cast(Callable[[int], pd.Series], getattr(y, "shift"))
        for L in lags:
            data[f"lag_{L}"] = shift_any(int(L))
        return pd.DataFrame(data)

    def train_xgboost(self, daily_ts: pd.DataFrame) -> object:
        if XGBRegressor is None:
            raise ImportError("xgboost not installed; add 'xgboost' to requirements to enable")
        if daily_ts.empty:
            raise ValueError("Empty time series for training")
        df = daily_ts.copy()
        to_dt_any: Callable[..., object] = cast(Callable[..., object], getattr(pd, "to_datetime"))
        df.loc[:, "ds"] = cast(pd.Series, to_dt_any(df["ds"]))
        # features
        feats_time = self._make_time_features(cast(pd.Series, df["ds"]))
        lags_df = self._add_lags(cast(pd.Series, df["y"]), [1, 7])
        X = pd.concat([feats_time, lags_df], axis=1)
        y = np.asarray(df["y"], dtype=float)
        # drop NA rows created by lags using numpy ops to avoid pandas stub Unknowns
        to_np_any: Callable[..., object] = cast(Callable[..., object], getattr(X, "to_numpy"))
        X_np = cast(NDArray[np.float64], to_np_any(dtype=float))
        valid_np: NDArray[np.bool_] = cast(NDArray[np.bool_], ~np.isnan(X_np).any(axis=1))
        Xv: pd.DataFrame = cast(pd.DataFrame, X.loc[valid_np])
        yv = y[valid_np]
        reg_ctor: Callable[..., RegressorProto] = XGBRegressor
        reg = reg_ctor(n_estimators=200, max_depth=4, learning_rate=0.1, subsample=0.9, colsample_bytree=0.8, random_state=42)
        fit_any: Callable[..., object] = cast(Callable[..., object], getattr(reg, "fit"))
        _ = fit_any(Xv, yv)
        rows_count = int(np.count_nonzero(valid_np))
        _log_ml(logging.INFO, "engine_xgb_train_end", rows=rows_count)
        return reg

    def forecast_sales_xgboost(self, model: object, daily_ts: pd.DataFrame, horizon_days: int = 14) -> pd.DataFrame:
        if XGBRegressor is None:
            raise ImportError("xgboost not installed; add 'xgboost' to requirements to enable")
        if daily_ts.empty:
            return pd.DataFrame({
                "ds": pd.Series(dtype="datetime64[ns]"),
                "yhat": pd.Series(dtype=float),
                "yhat_lower": pd.Series(dtype=float),
                "yhat_upper": pd.Series(dtype=float),
            })
        df = daily_ts.copy()
        to_dt_any: Callable[..., object] = cast(Callable[..., object], getattr(pd, "to_datetime"))
        df.loc[:, "ds"] = cast(pd.Series, to_dt_any(df["ds"]))
        # iterative forecast using last known y for lags
        last_ds = cast(pd.Timestamp, df["ds"].iloc[-1])
        y_hist: list[float] = list(np.asarray(df["y"], dtype=float))
        preds: list[float] = []
        dates: list[pd.Timestamp] = []
        for h in range(int(horizon_days)):
            cur_ds = cast(pd.Timestamp, last_ds + pd.Timedelta(days=h + 1))
            dates.append(cur_ds)
            feats_time = self._make_time_features(pd.Series([cur_ds]))
            # build lag features from y_hist
            y_series = pd.Series(y_hist)
            tmp_lag_df: pd.DataFrame = cast(pd.DataFrame, self._add_lags(y_series, [1, 7]).iloc[[-1]])
            fillna1: Callable[..., object] = cast(Callable[..., object], getattr(tmp_lag_df, "fillna"))
            lag_df = cast(pd.DataFrame, fillna1(method="ffill"))
            fillna2: Callable[..., object] = cast(Callable[..., object], getattr(lag_df, "fillna"))
            lag_df = cast(pd.DataFrame, fillna2(y_hist[-1]))
            Xh = pd.concat([feats_time.reset_index(drop=True), lag_df.reset_index(drop=True)], axis=1)
            pred_obj = cast(Callable[..., object], getattr(model, "predict"))(Xh)
            # Ensure scalar float
            pred_arr = np.asarray(pred_obj, dtype=float).ravel()
            pred = float(pred_arr[0] if pred_arr.size > 0 else np.nan)
            preds.append(pred)
            y_hist.append(pred)
        yhat = np.asarray(preds, dtype=float)
        # Simple CI via rolling std of history
        wnd = int(min(30, max(1, len(df))))
        sig = float(np.nanstd(np.asarray(df["y"], dtype=float)[-wnd:]) if wnd > 1 else 0.0)
        lo = yhat - 1.28 * sig
        hi = yhat + 1.28 * sig
        out = pd.DataFrame({
            "ds": pd.Series(dates),
            "yhat": yhat,
            "yhat_lower": lo,
            "yhat_upper": hi,
        })
        _log_ml(logging.INFO, "engine_xgb_forecast", horizon_days=int(horizon_days), rows=int(len(out)))
        return out

    def detect_anomalies_stl(self, daily_ts: pd.DataFrame, period: int = 7, z_thresh: float = 3.0) -> pd.DataFrame:
        if daily_ts.empty:
            return pd.DataFrame(
                {
                    "ds": pd.Series(dtype="datetime64[ns]"),
                    "y": pd.Series(dtype=float),
                    "is_anomaly": pd.Series(dtype=bool),
                    "score": pd.Series(dtype=float),
                }
            )
        y = np.asarray(daily_ts["y"], dtype=float)
        stl_ctor: Callable[..., object] = cast(Callable[..., object], getattr(sm_seasonal, "STL"))
        stl = stl_ctor(y, period=int(max(2, period)), robust=True)
        fit_fn: Callable[..., object] = cast(Callable[..., object], getattr(stl, "fit"))
        res = fit_fn()
        remainder_obj: NDArray[np.float64] = cast(NDArray[np.float64], getattr(res, "resid"))
        remainder = remainder_obj
        mu = float(np.nanmean(remainder))
        sigma = float(np.nanstd(remainder) + 1e-6)
        z = (remainder - mu) / sigma
        out = daily_ts.copy()
        out["is_anomaly"] = pd.Series(np.abs(z) > float(z_thresh), index=out.index)
        out["score"] = pd.Series(np.abs(z), index=out.index)
        mask_z: NDArray[np.bool_] = (np.abs(z) > float(z_thresh))
        _log_ml(
            logging.INFO,
            "engine_stl_detect",
            rows=int(len(out)),
            period=int(period),
            z_thresh=float(z_thresh),
            anomalies=int(np.count_nonzero(mask_z)),
        )
        return cast(pd.DataFrame, out.loc[:, ["ds", "y", "is_anomaly", "score"]])

    def detect_anomalies_stl_residuals(
        self,
        model: object,
        daily_ts: pd.DataFrame,
        model_type: str,
        period: int = 7,
        z_thresh: float = 3.0,
    ) -> pd.DataFrame:
        if daily_ts.empty:
            return pd.DataFrame(
                {
                    "ds": pd.Series(dtype="datetime64[ns]"),
                    "y": pd.Series(dtype=float),
                    "is_anomaly": pd.Series(dtype=bool),
                    "score": pd.Series(dtype=float),
                }
            )
        if model_type == "prophet":
            ins = self.insample_forecast_prophet(cast(Prophet, model), daily_ts)
        else:
            ins = self.insample_forecast_sarimax(model, daily_ts)
        merge_fn: Callable[..., object] = cast(Callable[..., object], getattr(pd, "merge"))
        merged = cast(pd.DataFrame, merge_fn(pd.DataFrame(daily_ts), pd.DataFrame(ins), on="ds", how="inner"))
        if merged.empty:
            return self.detect_anomalies_stl(daily_ts, period=period, z_thresh=z_thresh)
        y = np.asarray(merged["y"], dtype=float)
        yhat = np.asarray(merged["yhat"], dtype=float)
        resid = y - yhat
        stl_ctor2: Callable[..., object] = cast(Callable[..., object], getattr(sm_seasonal, "STL"))
        stl2 = stl_ctor2(resid, period=int(max(2, period)), robust=True)
        fit_fn2: Callable[..., object] = cast(Callable[..., object], getattr(stl2, "fit"))
        res2 = fit_fn2()
        remainder_obj2: NDArray[np.float64] = cast(NDArray[np.float64], getattr(res2, "resid"))
        remainder = remainder_obj2
        mu = float(np.nanmean(remainder))
        sigma = float(np.nanstd(remainder) + 1e-6)
        z = (remainder - mu) / sigma
        out = merged.copy()
        out["is_anomaly"] = pd.Series(np.abs(z) > float(z_thresh), index=out.index)
        out["score"] = pd.Series(np.abs(z), index=out.index)
        mask_z2: NDArray[np.bool_] = (np.abs(z) > float(z_thresh))
        _log_ml(
            logging.INFO,
            "engine_stl_resid_detect",
            rows=int(len(out)),
            period=int(period),
            z_thresh=float(z_thresh),
            anomalies=int(np.count_nonzero(mask_z2)),
        )
        return cast(pd.DataFrame, out.loc[:, ["ds", "y", "is_anomaly", "score"]])
