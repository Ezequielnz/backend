from __future__ import annotations

import logging
import json
import time
from datetime import datetime, timezone, date
from typing import Callable, cast, SupportsFloat, SupportsInt, SupportsIndex, TypeAlias, Protocol
from collections.abc import Sequence

import numpy as np
import math
import numbers
import pandas as pd
import importlib
from prophet import Prophet
from numpy.typing import NDArray
from supabase.client import Client

from app.db.supabase_client import get_supabase_service_client, TableQueryProto
from .feature_engineer import FeatureEngineer
from .ml_engine import BusinessMLEngine
from .model_version_manager import ModelVersionManager
from .recommendation_engine import check_stock_recommendations, check_sales_review_recommendations
from app.config.ml_settings import ml_settings
from app.workers.ml_worker import compute_anomaly_attributions

logger = logging.getLogger(__name__)

JSONLike: TypeAlias = None | bool | int | float | str | list["JSONLike"] | dict[str, "JSONLike"]

class HasToList(Protocol):
    def tolist(self) -> object: ...


class CeleryTaskProto(Protocol):
    def delay(self, *args: object, **kwargs: object) -> object: ...

def _log_ml(level: int, event: str, **fields: object) -> None:
    """Emit structured JSON logs for ML pipeline events."""
    try:
        payload: dict[str, object] = {"event": event, **fields}
        logger.log(level, json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        logger.log(level, f"{event} | {fields}")


def _mape(y_true: NDArray[np.float64], y_pred: NDArray[np.float64]) -> float:
    denom = np.clip(np.abs(y_true), 1e-6, None)
    return float(np.mean(np.abs(y_true - y_pred) / denom))


def _smape(y_true: NDArray[np.float64], y_pred: NDArray[np.float64]) -> float:
    """Symmetric MAPE in [0, 2], commonly reported as 0..200%.
    We keep it in 0..2 range (not percentage).
    """
    denom = np.clip(np.abs(y_true) + np.abs(y_pred), 1e-6, None)
    return float(np.mean(2.0 * np.abs(y_pred - y_true) / denom))


def _mae(y_true: NDArray[np.float64], y_pred: NDArray[np.float64]) -> float:
    return float(np.mean(np.abs(y_true - y_pred)))


def _rmse(y_true: NDArray[np.float64], y_pred: NDArray[np.float64]) -> float:
    diff = y_true - y_pred
    mse = float(np.mean(np.square(diff)))
    return float(math.sqrt(mse))


def _compute_shap_attributions(
    model: object,
    model_type: str,
    data: pd.DataFrame,
    anomalous_indices: list[int],
    max_evals: int = 1000,
    timeout_seconds: float = 30.0,
    sample_size: int | None = None,
) -> dict[str, object]:
    """
    Compute SHAP attributions for anomalous points with performance controls.

    Args:
        model: Trained model
        model_type: Type of model ('isolation_forest', 'stl', etc.)
        data: Feature data
        anomalous_indices: Indices of anomalous points
        max_evals: Max evaluations for SHAP
        timeout_seconds: Timeout for computation
        sample_size: Sample size for background data

    Returns:
        Dict with attributions and metadata
    """
    shap = None  # predeclare for type checkers
    psutil = None  # predeclare for type checkers
    try:
        import shap  # type: ignore[assignment]
        import psutil  # type: ignore[assignment]
        import os
        SHAP_AVAILABLE = True
        PSUTIL_AVAILABLE = True
    except ImportError as e:
        logger.warning(f"Optional dependencies not available: {e}")
        SHAP_AVAILABLE = False
        PSUTIL_AVAILABLE = False
        import os  # os is standard
    start_time = time.perf_counter()
    attributions = {}
    errors = []

    # Resource monitoring
    process = None
    initial_memory = 0.0
    if PSUTIL_AVAILABLE:
        try:
            process = psutil.Process(os.getpid())
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        except Exception as e:
            errors.append(f"psutil init failed: {e}")
    if model_type == "isolation_forest" and hasattr(model, 'estimators_') and SHAP_AVAILABLE:
        # Use TreeExplainer for IsolationForest
        background_data = data
        if sample_size and len(background_data) > sample_size:
            background_data = background_data.sample(n=sample_size, random_state=42)

        explainer = shap.TreeExplainer(model, data=background_data)

        for idx in anomalous_indices[:10]:
            if time.perf_counter() - start_time > timeout_seconds:
                errors.append("Timeout exceeded")
                break

            try:
                instance = data.iloc[[idx]]
                shap_values = explainer(instance, max_evals=max_evals)
                attributions[str(idx)] = {
                    "shap_values": shap_values.values.tolist(),
                    "base_value": float(shap_values.base_values[0]),
                    "feature_names": data.columns.tolist(),
                }
            except Exception as e:
                errors.append(f"SHAP computation failed for index {idx}: {str(e)}")
                # Fallback: simple feature importance
                attributions[str(idx)] = {
                    "fallback": True,
                    "feature_importance": {col: float(data[col].iloc[idx]) for col in data.columns},
                }

    elif model_type == "isolation_forest" and hasattr(model, 'estimators_') and not SHAP_AVAILABLE:
        # Fallback for all anomalies when SHAP not available
        for idx in anomalous_indices[:10]:
            attributions[str(idx)] = {
                "fallback": True,
                "feature_importance": {col: float(data[col].iloc[idx]) for col in data.columns},
            }

    elif model_type == "stl":
        # For STL, use statistical explanation
        for idx in anomalous_indices[:10]:
            if time.perf_counter() - start_time > timeout_seconds:
                errors.append("Timeout exceeded")
                break

            try:
                # Simple explanation based on deviation from trend
                point = data.iloc[idx]
                trend = data['trend'].mean() if 'trend' in data.columns else 0
                seasonal = data['seasonal'].mean() if 'seasonal' in data.columns else 0
                resid = data['resid'].iloc[idx] if 'resid' in data.columns else point.get('y', 0)

                attributions[str(idx)] = {
                    "explanation": "Statistical anomaly detection",
                    "deviation_from_trend": float(resid - trend),
                    "seasonal_component": float(seasonal),
                    "residual": float(resid),
                }
            except Exception as e:
                errors.append(f"STL explanation failed for index {idx}: {str(e)}")

    else:
        # Fallback for other models
        for idx in anomalous_indices[:5]:
            attributions[str(idx)] = {
                "fallback": True,
                "message": f"No SHAP support for model type {model_type}",
                "feature_values": {col: float(data[col].iloc[idx]) for col in data.columns},
            }

    # Resource monitoring
    if PSUTIL_AVAILABLE and process is not None:
        try:
            final_memory = process.memory_info().rss / 1024 / 1024
            memory_used = final_memory - initial_memory
        except Exception as e:
            errors.append(f"psutil read failed: {e}")
            memory_used = 0.0
    else:
        memory_used = 0.0
    return {
        "attributions": attributions,
        "metadata": {
            "computation_time": time.perf_counter() - start_time,
            "memory_used_mb": memory_used,
            "anomalies_processed": len(attributions),
            "total_anomalies": len(anomalous_indices),
            "errors": errors,
        }
    }



def _to_iso_date_str(x: object) -> str:
    """
    Convert various date-like objects to 'YYYY-MM-DD'.
    Falls back to str(x), stripping whitespace and trimming time portion if present.
    """
    if isinstance(x, datetime):
        return x.date().isoformat()
    if isinstance(x, date):
        return x.isoformat()
    s = str(x).strip()
    if "T" in s:
        return s.split("T")[0]
    if " " in s:
        return s.split(" ")[0]
    return s


def train_and_predict_sales(
    business_id: str,
    horizon_days: int = 14,
    history_days: int = 365,
    include_anomaly: bool = True,
    model_version: str = "1.0",
    cv_folds: int | None = None,
    # Prophet params
    seasonality_mode: str | None = None,
    holidays_country: str | None = None,
    log_transform: bool | None = None,
    # Model selection
    model_candidates: str | list[str] | None = None,
    select_best: bool | None = None,
    cv_primary_metric: str | None = None,
    # SARIMAX params (as tuples or comma-separated strings)
    sarimax_order: object | None = None,
    sarimax_seasonal: object | None = None,
    # Anomaly detection
    anomaly_method: str | None = None,
    stl_period: int | None = None,
) -> dict[str, object]:
    """
    End-to-end training and prediction pipeline for sales forecasting and anomalies.

    Steps:
    - Extract daily sales time series
    - Split train/validation to compute MAPE -> accuracy
    - Train final Prophet on full history
    - Persist model in `ml_models` (BYTEA)
    - Forecast next N days and upsert into `ml_predictions` with type 'sales_forecast'
    - Optionally train IsolationForest and upsert recent anomalies with type 'sales_anomaly'
    """
    fe = FeatureEngineer()
    engine = BusinessMLEngine()
    store = ModelVersionManager()
    svc: Client = get_supabase_service_client()
    # Pre-bind typed table function to avoid unbound warnings later
    table_fn: Callable[[str], object] = cast(Callable[[str], object], getattr(svc, "table"))

    t0 = time.perf_counter()
    _log_ml(
        logging.INFO,
        "ml_pipeline_start",
        tenant_id=business_id,
        horizon_days=horizon_days,
        history_days=history_days,
        include_anomaly=include_anomaly,
    )

    # Resolve configuration defaults from centralized settings with per-tenant overrides
    overrides: dict[str, object] = ml_settings.get_tenant_overrides(business_id)
    def _ov(key: str, default: object) -> object:
        return overrides.get(key, default)

    cv_folds_used: int = int(cv_folds) if cv_folds is not None else int(cast(SupportsInt | SupportsIndex | str | bytes | bytearray, _ov("ML_CV_FOLDS", ml_settings.ML_CV_FOLDS)))
    seasonality_mode_used: str = (seasonality_mode or str(_ov("ML_SEASONALITY_MODE", ml_settings.ML_SEASONALITY_MODE))).strip()
    holidays_country_used: str = (holidays_country or str(_ov("ML_HOLIDAYS_COUNTRY", ml_settings.ML_HOLIDAYS_COUNTRY))).strip()
    log_transform_used: bool = bool(ml_settings.ML_LOG_TRANSFORM if log_transform is None else log_transform)
    select_best_used: bool = bool(ml_settings.ML_SELECT_BEST if select_best is None else select_best)
    cv_primary_metric_used: str = (cv_primary_metric or str(_ov("ML_CV_PRIMARY_METRIC", ml_settings.ML_CV_PRIMARY_METRIC))).strip().lower()
    anomaly_method_used: str = (anomaly_method or str(_ov("ML_ANOMALY_METHOD", ml_settings.ML_ANOMALY_METHOD))).strip().lower()
    stl_period_used: int = int(stl_period) if stl_period is not None else int(cast(SupportsInt | SupportsIndex | str | bytes | bytearray, _ov("ML_STL_PERIOD", ml_settings.ML_STL_PERIOD)))
    stl_zthresh_used: float = float(cast(SupportsFloat | str | bytes | bytearray, _ov("ML_STL_ZTHRESH", ml_settings.ML_STL_ZTHRESH)))

    # Parse model candidates
    if model_candidates is None:
        mc_raw = _ov("ML_MODEL_CANDIDATES", ml_settings.ML_MODEL_CANDIDATES)
    else:
        mc_raw = model_candidates
    if isinstance(mc_raw, str):
        candidates: list[str] = [s.strip().lower() for s in mc_raw.split(",") if s.strip()]
    else:
        candidates = [str(s).strip().lower() for s in cast(list[object], mc_raw)]
    if not candidates:
        candidates = ["prophet"]

    # Parse SARIMAX orders
    def _parse_tuple3(x: object) -> tuple[int, int, int]:
        if x is None:
            return (1, 1, 1)
        if isinstance(x, (list, tuple)):
            seq = cast(Sequence[object], x)
            if len(seq) >= 3:
                return (
                    int(cast(SupportsInt | SupportsIndex | str | bytes | bytearray, seq[0])),
                    int(cast(SupportsInt | SupportsIndex | str | bytes | bytearray, seq[1])),
                    int(cast(SupportsInt | SupportsIndex | str | bytes | bytearray, seq[2])),
                )
        s = str(cast(object, x)).strip()
        parts = [p for p in s.split(",") if p.strip()]
        if len(parts) >= 3:
            return (int(parts[0]), int(parts[1]), int(parts[2]))
        return (1, 1, 1)

    def _parse_tuple4(x: object) -> tuple[int, int, int, int] | None:
        if x is None:
            return None
        if isinstance(x, (list, tuple)):
            seq = cast(Sequence[object], x)
            if len(seq) >= 4:
                return (
                    int(cast(SupportsInt | SupportsIndex | str | bytes | bytearray, seq[0])),
                    int(cast(SupportsInt | SupportsIndex | str | bytes | bytearray, seq[1])),
                    int(cast(SupportsInt | SupportsIndex | str | bytes | bytearray, seq[2])),
                    int(cast(SupportsInt | SupportsIndex | str | bytes | bytearray, seq[3])),
                )
        s = str(cast(object, x)).strip()
        if not s:
            return None
        parts = [p for p in s.split(",") if p.strip()]
        if len(parts) >= 4:
            return (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
        return None

    sarimax_order_used = _parse_tuple3(sarimax_order if sarimax_order is not None else _ov("ML_SARIMAX_ORDER", ml_settings.ML_SARIMAX_ORDER))
    sarimax_seasonal_used = _parse_tuple4(sarimax_seasonal if sarimax_seasonal is not None else _ov("ML_SARIMAX_SEASONAL", ml_settings.ML_SARIMAX_SEASONAL))

    # 1) Features
    t_feat = time.perf_counter()
    ts: pd.DataFrame = fe.sales_timeseries_daily(business_id, days=history_days)
    if ts.empty or len(ts) < 7:
        logger.info("Not enough sales data to train model for tenant=%s", business_id)
        return {
            "tenant_id": business_id,
            "trained": False,
            "reason": "insufficient_data",
            "history_len": int(len(ts)),
        }
    # Cap history length to configured max window for performance
    max_window_days = int(cast(SupportsInt | SupportsIndex | str | bytes | bytearray, _ov("ML_MAX_TRAIN_WINDOW_DAYS", ml_settings.ML_MAX_TRAIN_WINDOW_DAYS)))
    if len(ts) > max_window_days:
        ts = ts.tail(max_window_days)
        logger.info(
            "[ML] History capped to last %s days tenant=%s original_rows=%s",
            int(max_window_days),
            business_id,
            int(len(ts)),
        )
    _log_ml(
        logging.INFO,
        "ml_features_extracted",
        tenant_id=business_id,
        rows=int(len(ts)),
        took_seconds=round(time.perf_counter() - t_feat, 3),
    )

    # 2) Validation via rolling cross-validation (forward chaining) with model selection
    metrics_summary: dict[str, object] = {}
    selected_model: str = "prophet"
    try:
        t_val = time.perf_counter()
        n = len(ts)
        min_train = 7
        possible_folds = max(0, min(int(cv_folds_used), (n - min_train) // max(1, int(horizon_days))))
        metrics_by_model: dict[str, dict[str, object]] = {}
        if possible_folds >= 1:
            for model_name in candidates:
                per_fold: list[dict[str, float]] = []
                total_train_time = 0.0
                total_infer_time = 0.0
                xgb_failed = False
                for i in range(possible_folds, 0, -1):
                    cutoff = n - i * int(horizon_days)
                    if cutoff <= min_train:
                        continue
                    head_fn: Callable[[int], pd.DataFrame] = cast(Callable[[int], pd.DataFrame], getattr(ts, "head"))
                    train_df: pd.DataFrame = head_fn(cutoff)
                    test_df: pd.DataFrame = cast(pd.DataFrame, ts.iloc[cutoff : cutoff + int(horizon_days)])
                    # Optional log transform on training target
                    if log_transform_used:
                        train_df_t = train_df.copy()
                        train_df_t.loc[:, "y"] = np.log1p(np.asarray(train_df_t["y"], dtype=float))
                    else:
                        train_df_t = train_df
                    t_fold_train = time.perf_counter()
                    if model_name == "sarimax":
                        exog_train = engine._make_time_features(cast(pd.Series, train_df_t["ds"]), business_id)[["is_holiday", "is_special_date"]]
                        m = engine.train_sarimax(train_df_t, order=sarimax_order_used, seasonal_order=sarimax_seasonal_used, exog=exog_train)
                    elif model_name == "prophet":
                        m = engine.train_sales_forecasting_prophet(
                            train_df_t,
                            seasonality_mode=seasonality_mode_used,
                            holidays_country=holidays_country_used,
                        )
                    elif model_name == "xgboost":
                        try:
                            m = engine.train_xgboost(train_df_t, business_id)
                        except Exception as ex:
                            _log_ml(logging.WARNING, "ml_cv_skip_model", tenant_id=business_id, model=model_name, reason=str(ex))
                            xgb_failed = True
                            break
                    else:
                        # Baseline models do not require training time
                        m = None
                    total_train_time += time.perf_counter() - t_fold_train
                    t_fold_fc = time.perf_counter()
                    if model_name == "sarimax":
                        # Create future exog
                        future_dates = pd.date_range(start=train_df_t["ds"].max() + pd.Timedelta(days=1), periods=int(horizon_days), freq="D")
                        exog_future = engine._make_time_features(pd.Series(future_dates), business_id)[["is_holiday", "is_special_date"]]
                        fcst = engine.forecast_sales_sarimax(m, horizon_days=int(horizon_days), exog=exog_future)
                        yhat = np.asarray(fcst["yhat"], dtype=float)
                    elif model_name == "prophet":
                        fcst = engine.forecast_sales_prophet(cast(Prophet, m), horizon_days=int(horizon_days))
                        # Align by date for Prophet
                        fcst = pd.DataFrame(fcst)
                        fcst["ds"] = [
                            _to_iso_date_str(x) for x in cast(list[object], cast(pd.Series, fcst["ds"]).tolist())
                        ]
                        test_df_iso: pd.DataFrame = pd.DataFrame(test_df)
                        test_df_iso["ds"] = [
                            _to_iso_date_str(x) for x in cast(list[object], cast(pd.Series, test_df_iso["ds"]).tolist())
                        ]
                        merged = cast(Callable[..., pd.DataFrame], getattr(test_df_iso, "merge"))(fcst, on="ds", how="inner")
                        yhat = np.asarray(merged["yhat"], dtype=float)
                        test_df = merged  # For Prophet alignment below
                    elif model_name == "xgboost":
                        if xgb_failed:
                            break
                        fcst = engine.forecast_sales_xgboost(m, train_df_t, horizon_days=int(horizon_days), tenant_id=business_id)
                        fcst = pd.DataFrame(fcst)
                        fcst["ds"] = [
                            _to_iso_date_str(x) for x in cast(list[object], cast(pd.Series, fcst["ds"]).tolist())
                        ]
                        test_df_iso2: pd.DataFrame = pd.DataFrame(test_df)
                        test_df_iso2["ds"] = [
                            _to_iso_date_str(x) for x in cast(list[object], cast(pd.Series, test_df_iso2["ds"]).tolist())
                        ]
                        merged2 = cast(Callable[..., pd.DataFrame], getattr(test_df_iso2, "merge"))(fcst, on="ds", how="inner")
                        yhat = np.asarray(merged2["yhat"], dtype=float)
                        test_df = merged2
                    else:
                        # Baselines: naive/snaive
                        train_y_arr: NDArray[np.float64] = np.asarray(cast(pd.Series, train_df["y"]), dtype=float)
                        if model_name == "snaive":
                            season: int = int(max(2, stl_period_used))
                            # use last season values repeated
                            last_season = train_y_arr[-season:] if len(train_df) >= season else train_y_arr[-1:]
                            num: float = float(int(horizon_days))
                            den: float = float(max(1, season))
                            ratio: float = num / den
                            ceil_val: float = float(math.ceil(ratio))
                            reps: int = int(ceil_val)
                            yhat = np.tile(last_season, reps)[: int(horizon_days)]
                        else:
                            # naive
                            last_val = float(cast(SupportsFloat, train_y_arr[-1]))
                            yhat = np.repeat(last_val, int(horizon_days))
                    total_infer_time += time.perf_counter() - t_fold_fc
                    # Invert transform if needed
                    if log_transform_used:
                        yhat = np.expm1(yhat)
                    # Evaluate against test
                    y_true = np.asarray(test_df["y"], dtype=float)
                    min_len = int(min(len(y_true), len(yhat)))
                    y_true_np: NDArray[np.float64] = cast(NDArray[np.float64], y_true[:min_len])
                    y_pred_np: NDArray[np.float64] = cast(NDArray[np.float64], yhat[:min_len])
                    if min_len == 0:
                        fold_mape = 0.5
                        fold_smape = 1.0
                        fold_mae = float(np.nan)
                        fold_rmse = float(np.nan)
                    else:
                        fold_mape = _mape(y_true_np, y_pred_np)
                        fold_smape = _smape(y_true_np, y_pred_np)
                        fold_mae = _mae(y_true_np, y_pred_np)
                        fold_rmse = _rmse(y_true_np, y_pred_np)
                    per_fold.append(
                        {
                            "mape": float(fold_mape),
                            "smape": float(fold_smape),
                            "mae": float(fold_mae),
                            "rmse": float(fold_rmse),
                            "train_rows": float(len(train_df)),
                            "test_rows": float(len(test_df)),
                        }
                    )
                # Aggregate per model
                def _mean(values: list[float]) -> float:
                    arr = np.asarray(values, dtype=float)
                    if arr.size == 0:
                        return float("nan")
                    return float(np.nanmean(arr))
                mape_mean = _mean([f["mape"] for f in per_fold]) if per_fold else 0.5
                smape_mean = _mean([f["smape"] for f in per_fold]) if per_fold else 1.0
                mae_mean = _mean([f["mae"] for f in per_fold]) if per_fold else float("nan")
                rmse_mean = _mean([f["rmse"] for f in per_fold]) if per_fold else float("nan")
                metrics_by_model[model_name] = {
                    "mape": float(mape_mean),
                    "smape": float(smape_mean),
                    "mae": float(mae_mean),
                    "rmse": float(rmse_mean),
                    "cv": {"folds": int(len(per_fold)), "horizon_days": int(horizon_days), "metrics_per_fold": per_fold},
                    "timing": {
                        "train_time": float(total_train_time),
                        "infer_time": float(total_infer_time),
                    },
                }
                _log_ml(
                    logging.INFO,
                    "ml_cv_result",
                    tenant_id=business_id,
                    model=model_name,
                    folds=int(len(per_fold)),
                    mape=float(mape_mean),
                    smape=float(smape_mean),
                    mae=float(mae_mean) if not np.isnan(mae_mean) else None,
                    rmse=float(rmse_mean) if not np.isnan(rmse_mean) else None,
                )
            # Select best model
            def _score(model_metrics: dict[str, object]) -> float:
                key = cv_primary_metric_used
                val = cast(float, model_metrics.get(key, float("inf")))
                return float(val)
            def _score_item(kv: tuple[str, dict[str, object]]) -> float:
                return _score(kv[1])
            if select_best_used and len(metrics_by_model) > 1 and cv_primary_metric_used in ("mape", "smape", "mae", "rmse"):
                selected_model = min(metrics_by_model.items(), key=_score_item)[0]
            else:
                selected_model = candidates[0]
            sel_metrics: dict[str, object] = metrics_by_model.get(selected_model) or {}
            mape = float(cast(SupportsFloat, sel_metrics.get("mape", 0.5)))
            metrics_summary = {
                "selected_model": selected_model,
                "mape": float(cast(SupportsFloat, sel_metrics.get("mape", float("nan")))),
                "smape": float(cast(SupportsFloat, sel_metrics.get("smape", float("nan")))),
                "mae": float(cast(SupportsFloat, sel_metrics.get("mae", float("nan")))),
                "rmse": float(cast(SupportsFloat, sel_metrics.get("rmse", float("nan")))),
                "cv": sel_metrics.get("cv") or {},
                "timing": sel_metrics.get("timing") or {},
                "candidate_metrics": metrics_by_model,
            }
        else:
            # Fallback: not enough data for CV; choose first candidate
            selected_model = candidates[0]
            mape = 0.5
            metrics_summary = {
                "selected_model": selected_model,
                "mape": 0.5,
                "smape": 1.0,
                "mae": float("nan"),
                "rmse": float("nan"),
                "cv": {"folds": 0},
            }
        accuracy = float(max(0.0, min(1.0, 1.0 - mape)))
        _log_ml(
            logging.INFO,
            "ml_validation_completed",
            tenant_id=business_id,
            folds=int(possible_folds),
            took_seconds=round(time.perf_counter() - t_val, 3),
        )
        # Drift monitoring: alert when MAPE exceeds threshold
        try:
            drift_thresh = float(ml_settings.ML_ERROR_ALERT_MAPE)
        except Exception:
            drift_thresh = float("nan")
        if not np.isnan(drift_thresh) and drift_thresh > 0 and not np.isnan(mape) and mape > drift_thresh:
            try:
                mod = importlib.import_module("app.workers.notification_worker")
                _notify: CeleryTaskProto = cast(CeleryTaskProto, getattr(mod, "send_notification"))
                msg: dict[str, object] = {
                    "title": "Alerta de precisión de pronóstico",
                    "message": f"MAPE actual {mape:.3f} supera umbral {drift_thresh:.3f}",
                    "severity": "warning",
                    "metrics": {"mape": mape, "threshold": drift_thresh},
                    "selected_model": selected_model,
                }
                _ = _notify.delay(business_id, "ml_drift_alert", msg)
                _log_ml(logging.WARNING, "ml_drift_alert_queued", tenant_id=business_id, mape=float(mape), threshold=float(drift_thresh))
            except Exception as _e:
                _log_ml(logging.WARNING, "ml_drift_alert_error", tenant_id=business_id, error=str(_e))
    except Exception as e:
        logger.warning("Validation error for tenant=%s: %s", business_id, e)
        accuracy = 0.5
        metrics_summary = {
            "selected_model": selected_model,
            "mape": 0.5,
            "smape": 1.0,
            "mae": float("nan"),
            "rmse": float("nan"),
            "cv": {"folds": 0},
            "error": str(e),
        }

    # 3) Train final model on full series
    t_train = time.perf_counter()
    # Optional log transform for final training
    if log_transform_used:
        ts_train = ts.copy()
        ts_train.loc[:, "y"] = np.log1p(np.asarray(ts_train["y"], dtype=float))
    else:
        ts_train = ts
    # Predeclare model for typing across branches
    model: object
    if selected_model == "sarimax":
        exog_train_full = engine._make_time_features(cast(pd.Series, ts_train["ds"]), business_id)[["is_holiday", "is_special_date"]]
        model = engine.train_sarimax(ts_train, order=sarimax_order_used, seasonal_order=sarimax_seasonal_used, exog=exog_train_full)
    elif selected_model == "prophet":
        model = engine.train_sales_forecasting_prophet(
            ts_train,
            seasonality_mode=seasonality_mode_used,
            holidays_country=holidays_country_used,
        )
    elif selected_model == "xgboost":
        try:
            model = engine.train_xgboost(ts_train, business_id)
        except Exception as ex:
            _log_ml(logging.WARNING, "ml_train_xgb_failed_fallback", tenant_id=business_id, reason=str(ex))
            # Prefer baseline fallback if available among candidates to avoid heavy training
            # Preserve candidate order preference: choose the first available among (snaive, naive)
            baseline_choice = None
            for cand in candidates:
                if cand in ("snaive", "naive"):
                    baseline_choice = cand
                    break
            if baseline_choice is not None:
                selected_model = baseline_choice
                model = cast(object, {"type": "baseline", "variant": selected_model, "season": int(stl_period_used)})
            else:
                # Fallback to Prophet
                model = engine.train_sales_forecasting_prophet(
                    ts_train,
                    seasonality_mode=seasonality_mode_used,
                    holidays_country=holidays_country_used,
                )
                selected_model = "prophet"
    else:
        # Baselines: store minimal config
        model = cast(object, {"type": "baseline", "variant": selected_model, "season": int(stl_period_used)})
    _log_ml(
        logging.INFO,
        "ml_final_training",
        tenant_id=business_id,
        model=selected_model,
        rows=int(len(ts)),
        took_seconds=round(time.perf_counter() - t_train, 3),
    )
    # Ensure metrics_summary reflects any fallback-adjusted selection
    try:
        metrics_summary["selected_model"] = selected_model
    except Exception:
        pass

    # 4) Persist model
    t_save = time.perf_counter()
    # Sanitize metrics for JSON (replace NaN/Inf with None, convert numpy types)
    def _json_sanitize(obj: object) -> JSONLike:
        try:
            import numpy as _np  # local import to avoid top-level stubs conflicts
            import math as _math
            if obj is None:
                return None
            # Strings and booleans are safe scalars
            elif isinstance(obj, (str, bool)):
                return cast(JSONLike, obj)
            # Integers first (bool is subclass of int, but handled above)
            elif isinstance(obj, numbers.Integral):
                return int(obj)
            # Real numbers (np.floating, float) excluding integrals
            elif isinstance(obj, numbers.Real):
                v: float = float(obj)
                if not _math.isfinite(v):
                    return None
                return v
            elif isinstance(obj, (list, tuple)):
                seq = cast(Sequence[object], obj)
                return [ _json_sanitize(x) for x in seq ]
            elif isinstance(obj, _np.ndarray):
                # Use a minimal protocol to avoid strict numpy ndarray generics
                arr_obj: HasToList = cast(HasToList, obj)
                lst_obj: object = arr_obj.tolist()
                if isinstance(lst_obj, list):
                    lst: list[object] = cast(list[object], lst_obj)
                    return [ _json_sanitize(x) for x in lst ]
                # Scalar ndarray tolist() returns a scalar
                return _json_sanitize(lst_obj)
            elif isinstance(obj, dict):
                m = cast(dict[object, object], obj)
                return { str(k): _json_sanitize(v) for k, v in m.items() }
            # Fallback: coerce unknown objects to string for JSON safety
            return str(obj)
        except Exception:
            # On any unexpected error, return stringified object to guarantee JSON-serializable
            return str(obj)  # pyright: ignore[reportUnknownArgumentType]

    metrics_payload_obj: dict[str, object] = {
        # Aggregate metrics at top-level for convenience
        "mape": cast(float, metrics_summary.get("mape", float(1.0 - accuracy))),
        "smape": cast(float, metrics_summary.get("smape", float("nan"))),
        "mae": cast(float, metrics_summary.get("mae", float("nan"))),
        "rmse": cast(float, metrics_summary.get("rmse", float("nan"))),
        # Full CV detail (if available)
        "cv": cast(object, metrics_summary.get("cv") or {}),
        "timing": cast(object, metrics_summary.get("timing") or {}),
        "selected_model": selected_model,
        "candidate_metrics": cast(object, metrics_summary.get("candidate_metrics") or {}),
    }
    training_metrics_payload = _json_sanitize(metrics_payload_obj)

    saved = store.save_model(
        tenant_id=business_id,
        model_type="sales_forecasting",
        model=model,
        model_version=model_version,
        hyperparameters={
            "horizon_days": horizon_days,
            "cv_folds": int(cv_folds_used),
            "seasonality_mode": seasonality_mode_used,
            "holidays_country": holidays_country_used,
            "log_transform": bool(log_transform_used),
            "selected_model": selected_model,
            "model_candidates": candidates,
            "cv_primary_metric": cv_primary_metric_used,
            "sarimax_order": list(sarimax_order_used),
            "sarimax_seasonal": list(sarimax_seasonal_used) if isinstance(sarimax_seasonal_used, tuple) else sarimax_seasonal_used,
            "anomaly_method": anomaly_method_used,
            "stl_period": int(stl_period_used),
            "stl_zthresh": float(stl_zthresh_used),
            "baseline_variant": (selected_model if selected_model in ("naive", "snaive") else None),
        },
        training_metrics=cast(dict[str, object], training_metrics_payload),
        accuracy=accuracy,
        is_active=True,
    )
    _log_ml(
        logging.INFO,
        "ml_model_saved",
        tenant_id=business_id,
        model_id=saved.id,
        took_seconds=round(time.perf_counter() - t_save, 3),
    )

    # 5) Forecast and upsert predictions (batch)
    t_fc = time.perf_counter()
    fcst: pd.DataFrame
    if selected_model == "sarimax":
        # Create future exog for forecast
        future_dates_full = pd.date_range(start=ts_train["ds"].max() + pd.Timedelta(days=1), periods=horizon_days, freq="D")
        exog_future_full = engine._make_time_features(pd.Series(future_dates_full), business_id)[["is_holiday", "is_special_date"]]
        fcst = engine.forecast_sales_sarimax(model, horizon_days=horizon_days, exog=exog_future_full)
    elif selected_model == "prophet":
        fcst = engine.forecast_sales_prophet(cast(Prophet, model), horizon_days=horizon_days)
    elif selected_model == "xgboost":
        fcst = engine.forecast_sales_xgboost(model, ts_train, horizon_days=horizon_days, tenant_id=business_id)
    else:
        if selected_model == "snaive":
            fcst = engine.forecast_baseline_snaive(ts, horizon_days=horizon_days, season=int(max(2, stl_period_used)))
        else:
            fcst = engine.forecast_baseline_naive(ts, horizon_days=horizon_days)
    if log_transform_used:
        # Invert transform for outputs
        if not fcst.empty:
            fcst = fcst.copy()
            fcst.loc[:, "yhat"] = np.expm1(np.asarray(fcst["yhat"], dtype=float))
            if "yhat_lower" in fcst.columns:
                fcst.loc[:, "yhat_lower"] = np.expm1(np.asarray(fcst["yhat_lower"], dtype=float))
            if "yhat_upper" in fcst.columns:
                fcst.loc[:, "yhat_upper"] = np.expm1(np.asarray(fcst["yhat_upper"], dtype=float))
    # Compute a simple recent stddev for fallback intervals when model doesn't provide them
    wnd = int(min(30, max(1, len(ts))))
    sig_recent = float(np.nanstd(np.asarray(ts["y"], dtype=float)[-wnd:]) if wnd > 1 else 0.0)
    payloads: list[dict[str, object]] = []
    for _, row in fcst.iterrows():
        pred_ds_obj: object = cast(object, row["ds"])
        yhat = float(cast(SupportsFloat, row["yhat"]))
        ylo = float(cast(SupportsFloat, row["yhat_lower"]))
        yhi = float(cast(SupportsFloat, row["yhat_upper"]))
        # Fallback/sanitization to avoid NaNs or invalid intervals from some model outputs
        try:
            import math as _math
            if not _math.isfinite(yhat):
                arr_last: NDArray[np.float64] = cast(NDArray[np.float64], np.asarray(ts["y"], dtype=float))
                last_val = float(cast(SupportsFloat, arr_last.item(-1))) if arr_last.size > 0 else 0.0
                yhat = last_val
            if not (_math.isfinite(ylo) and _math.isfinite(yhi)):
                ylo = yhat - 1.28 * sig_recent
                yhi = yhat + 1.28 * sig_recent
            if ylo > yhi:
                ylo, yhi = yhi, ylo
            # Ensure the point forecast lies within the interval
            ylo = min(ylo, yhat)
            yhi = max(yhi, yhat)
        except Exception:
            # On any unexpected issue, at least provide a narrow interval around yhat
            ylo = yhat
            yhi = yhat
        width = abs(yhi - ylo)
        denom = max(abs(yhat), 1e-6)
        conf = float(max(0.0, min(1.0, 1.0 / (1.0 + width / denom))))
        payloads.append(
            {
                "tenant_id": business_id,
                "model_id": saved.id,
                "prediction_date": _to_iso_date_str(pred_ds_obj),
                "prediction_type": "sales_forecast",
                "predicted_values": {
                    "yhat": yhat,
                    "yhat_lower": ylo,
                    "yhat_upper": yhi,
                },
                "confidence_score": conf,
            }
        )
    inserted = 0
    if payloads:
        chunk = 200
        for i in range(0, len(payloads), chunk):
            pred_tbl: TableQueryProto = cast(TableQueryProto, table_fn("ml_predictions"))
            _ = pred_tbl.upsert(payloads[i : i + chunk], on_conflict="tenant_id,prediction_date,prediction_type").execute()
            inserted += len(payloads[i : i + chunk])
    _log_ml(
        logging.INFO,
        "ml_forecast_upsert",
        tenant_id=business_id,
        rows=inserted,
        took_seconds=round(time.perf_counter() - t_fc, 3),
    )

    anomalies_summary: dict[str, object] | None = None
    if include_anomaly:
        try:
            t_an = time.perf_counter()
            records: list[dict[str, object]] = []
            if anomaly_method_used == "stl_resid":
                # Build residuals with consistent scale
                ins: pd.DataFrame | None = None
                if selected_model == "sarimax":
                    ins = engine.insample_forecast_sarimax(model, ts_train)
                elif selected_model == "prophet":
                    ins = engine.insample_forecast_prophet(cast(Prophet, model), ts_train)
                else:
                    # Fallback for baseline/xgboost: detect over original series
                    an = engine.detect_anomalies_stl(ts, period=int(stl_period_used), z_thresh=stl_zthresh_used)
                    to_dict_an_fn2: Callable[..., object] = cast(Callable[..., object], getattr(an, "to_dict"))
                    recs_obj2 = to_dict_an_fn2(orient="records")
                    records = cast(list[dict[str, object]], recs_obj2) if not an.empty else []
                    ins = None
                if ins is not None:
                    df_ts_for_merge: pd.DataFrame = pd.DataFrame(ts_train)
                    df_ins_for_merge: pd.DataFrame = pd.DataFrame(ins)
                    merge_fn1: Callable[..., pd.DataFrame] = cast(Callable[..., pd.DataFrame], getattr(df_ts_for_merge, "merge"))
                    merged = merge_fn1(df_ins_for_merge, on="ds", how="inner")
                    if not merged.empty:
                        resid = np.asarray(merged["y"], dtype=float) - np.asarray(merged["yhat"], dtype=float)
                        resid_ts = pd.DataFrame({"ds": merged["ds"], "y": resid})
                        an_resid = engine.detect_anomalies_stl(resid_ts, period=int(stl_period_used), z_thresh=stl_zthresh_used)
                        # Join with original y for output
                        left_df: pd.DataFrame = cast(pd.DataFrame, an_resid[["ds", "is_anomaly", "score"]])
                        right_df: pd.DataFrame = cast(pd.DataFrame, ts[["ds", "y"]])
                        merge_fn2: Callable[..., pd.DataFrame] = cast(Callable[..., pd.DataFrame], getattr(left_df, "merge"))
                        an_join = merge_fn2(right_df, on="ds", how="left")
                        to_dict_join_fn: Callable[..., object] = cast(Callable[..., object], getattr(an_join, "to_dict"))
                        recs_obj = to_dict_join_fn(orient="records")
                        records = cast(list[dict[str, object]], recs_obj) if not an_join.empty else []
            else:
                iso = engine.train_anomaly_detection(ts)
                an: pd.DataFrame = engine.detect_anomalies(iso, ts)
                to_dict_an_fn: Callable[..., object] = cast(Callable[..., object], getattr(an, "to_dict"))
                recs_obj = to_dict_an_fn(orient="records")
                records = cast(list[dict[str, object]], recs_obj) if not an.empty else []
            if records:
                records.sort(key=lambda rec: _to_iso_date_str(cast(object, rec.get("ds"))))
                records = records[-30:]
            a_payloads: list[dict[str, object]] = []
            for rec in records:
                is_anom_obj: object | None = rec.get("is_anomaly")
                is_anom = bool(is_anom_obj) if is_anom_obj is not None else False
                if is_anom:
                    anom_ds_obj: object = cast(object, rec.get("ds"))
                    y_val = rec.get("y")
                    score_obj: object | None = rec.get("score")
                    y = float(cast(SupportsFloat, y_val)) if y_val is not None else 0.0
                    score = float(cast(SupportsFloat, score_obj)) if score_obj is not None else 0.0
                    conf = float(1.0 / (1.0 + math.exp(5.0 * score)))
                    a_payloads.append(
                        {
                            "tenant_id": business_id,
                            "model_id": saved.id,
                            "prediction_date": _to_iso_date_str(anom_ds_obj),
                            "prediction_type": "sales_anomaly",
                            "predicted_values": {
                                "y": y,
                                "score": score,
                                "is_anomaly": True,
                            },
                            "confidence_score": max(0.0, min(1.0, conf)),
                        }
                    )
            a_inserted = 0
            if a_payloads:
                chunk = 200
                for i in range(0, len(a_payloads), chunk):
                    anom_tbl: TableQueryProto = cast(TableQueryProto, table_fn("ml_predictions"))
                    _ = anom_tbl.upsert(a_payloads[i : i + chunk], on_conflict="tenant_id,prediction_date,prediction_type").execute()
                    a_inserted += len(a_payloads[i : i + chunk])
            _log_ml(
                logging.INFO,
                "ml_anomaly_upsert",
                tenant_id=business_id,
                rows=a_inserted,
                took_seconds=round(time.perf_counter() - t_an, 3),
            )

            # Phase 1: Async SHAP Attribution Computation
            attribution_summary = {}
            if a_inserted > 0 and records:
                try:
                    # Determine model type for attributions
                    model_type = "stl" if anomaly_method_used == "stl_resid" else "isolation_forest"

                    # Get the anomaly model for attributions
                    anomaly_model = None
                    if anomaly_method_used == "stl_resid":
                        anomaly_model = model  # Use the forecasting model
                    else:
                        anomaly_model = engine.train_anomaly_detection(ts)  # IsolationForest

                    # Trigger async attribution computation
                    cast(CeleryTaskProto, compute_anomaly_attributions).delay(
                        business_id,
                        records,
                        anomaly_model,
                        model_type
                    )

                    attribution_summary = {
                        "task_triggered": True,
                        "anomalies_count": len([r for r in records if r.get("is_anomaly")]),
                        "model_type": model_type,
                    }

                    _log_ml(
                        logging.INFO,
                        "ml_attribution_task_queued",
                        tenant_id=business_id,
                        anomalies=len([r for r in records if r.get("is_anomaly")]),
                        model_type=model_type,
                    )

                except Exception as e:
                    logger.warning("Failed to queue attribution task for tenant=%s: %s", business_id, e)
                    attribution_summary = {"error": str(e), "task_triggered": False}

            anomalies_summary = {"inserted": a_inserted, "attributions": attribution_summary}
        except Exception as e:
            logger.warning("Anomaly pipeline failed for tenant=%s: %s", business_id, e)
            anomalies_summary = {"inserted": 0, "error": str(e)}

    # 6) Generate recommendations
    recommendations_summary: dict[str, object] = {}
    try:
        stock_recs = check_stock_recommendations(business_id)
        sales_recs = check_sales_review_recommendations(business_id)
        recommendations_summary = {"stock_recommendations": stock_recs, "sales_recommendations": sales_recs}
        _log_ml(
            logging.INFO,
            "ml_recommendations_generated",
            tenant_id=business_id,
            stock_recs=stock_recs,
            sales_recs=sales_recs,
        )
    except Exception as e:
        logger.warning("Recommendations failed for tenant=%s: %s", business_id, e)
        recommendations_summary = {"error": str(e)}

    total_time = time.perf_counter() - t0
    _log_ml(
        logging.INFO,
        "ml_pipeline_end",
        tenant_id=business_id,
        model_id=saved.id,
        model=metrics_summary.get("selected_model"),
        accuracy=accuracy,
        forecasts=inserted,
        anomalies=anomalies_summary.get("inserted") if anomalies_summary else None,
        took_seconds=round(total_time, 3),
    )
    return {
        "tenant_id": business_id,
        "trained": True,
        "model_id": saved.id,
        "accuracy": accuracy,
        "forecasts_inserted": inserted,
        "anomalies": anomalies_summary,
        "recommendations": recommendations_summary,
        "selected_model": metrics_summary.get("selected_model"),
        "metrics_summary": metrics_summary,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
