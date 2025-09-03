from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, date
from typing import Callable, cast, SupportsFloat

import numpy as np
import math
import pandas as pd
from numpy.typing import NDArray
from supabase.client import Client

from app.db.supabase_client import get_supabase_service_client, TableQueryProto
from .feature_engineer import FeatureEngineer
from .ml_engine import BusinessMLEngine
from .model_version_manager import ModelVersionManager

logger = logging.getLogger(__name__)


def _mape(y_true: NDArray[np.float64], y_pred: NDArray[np.float64]) -> float:
    denom = np.clip(np.abs(y_true), 1e-6, None)
    return float(np.mean(np.abs(y_true - y_pred) / denom))


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
    logger.info(
        "[ML] Pipeline start tenant=%s horizon_days=%s history_days=%s include_anomaly=%s",
        business_id,
        horizon_days,
        history_days,
        include_anomaly,
    )

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
    # Cap history length to last 730 days for performance
    if len(ts) > 730:
        ts = ts.tail(730)
        logger.info(
            "[ML] History capped to last 730 days tenant=%s original_rows=%s",
            business_id,
            int(len(ts)),
        )
    logger.info(
        "[ML] Features extracted tenant=%s rows=%s took=%.2fs",
        business_id,
        int(len(ts)),
        time.perf_counter() - t_feat,
    )

    # 2) Validation split for accuracy
    try:
        t_val = time.perf_counter()
        if len(ts) >= 2 * horizon_days + 7:
            train_df: pd.DataFrame = ts.head(len(ts) - horizon_days)
            test_df: pd.DataFrame = ts.tail(horizon_days)
            t_val_train = time.perf_counter()
            m1 = engine.train_sales_forecasting(train_df)
            train_time = time.perf_counter() - t_val_train
            t_val_fc = time.perf_counter()
            val_fcst: pd.DataFrame = engine.forecast_sales(m1, horizon_days=horizon_days)
            fc_time = time.perf_counter() - t_val_fc
            # Align by date using safe string conversions
            val_fcst = pd.DataFrame(val_fcst)
            val_ds_list: list[object] = cast(list[object], cast(pd.Series, val_fcst["ds"]).tolist())
            val_fcst["ds"] = [_to_iso_date_str(x) for x in val_ds_list]
            test_df_iso: pd.DataFrame = pd.DataFrame(test_df)
            test_ds_list: list[object] = cast(list[object], cast(pd.Series, test_df_iso["ds"]).tolist())
            test_df_iso["ds"] = [_to_iso_date_str(x) for x in test_ds_list]
            merge_method: Callable[..., pd.DataFrame] = cast(Callable[..., pd.DataFrame], getattr(test_df_iso, "merge"))
            merged: pd.DataFrame = merge_method(val_fcst, on="ds", how="inner")
            if not merged.empty:
                y_true_np: NDArray[np.float64] = cast(NDArray[np.float64], np.asarray(merged["y"], dtype=float))
                y_pred_np: NDArray[np.float64] = cast(NDArray[np.float64], np.asarray(merged["yhat"], dtype=float))
                mape = _mape(y_true_np, y_pred_np)
            else:
                mape = 0.5  # default if merge failed
            logger.info(
                "[ML] Validation tenant=%s train_rows=%s mape=%.4f train_time=%.2fs infer_time=%.2fs took=%.2fs",
                business_id,
                int(len(train_df)),
                float(mape),
                train_time,
                fc_time,
                time.perf_counter() - t_val,
            )
        else:
            mape = 0.5
        accuracy = float(max(0.0, min(1.0, 1.0 - mape)))
    except Exception as e:
        logger.warning("Validation error for tenant=%s: %s", business_id, e)
        accuracy = 0.5

    # 3) Train final model on full series
    t_train = time.perf_counter()
    model = engine.train_sales_forecasting(ts)
    logger.info(
        "[ML] Final training tenant=%s rows=%s took=%.2fs",
        business_id,
        int(len(ts)),
        time.perf_counter() - t_train,
    )

    # 4) Persist model
    t_save = time.perf_counter()
    saved = store.save_model(
        tenant_id=business_id,
        model_type="sales_forecasting",
        model=model,
        model_version=model_version,
        hyperparameters={"horizon_days": horizon_days},
        training_metrics={"mape": float(1.0 - accuracy)},
        accuracy=accuracy,
        is_active=True,
    )
    logger.info(
        "[ML] Model saved tenant=%s model_id=%s took=%.2fs",
        business_id,
        saved.id,
        time.perf_counter() - t_save,
    )

    # 5) Forecast and upsert predictions (batch)
    t_fc = time.perf_counter()
    fcst: pd.DataFrame = engine.forecast_sales(model, horizon_days=horizon_days)
    payloads: list[dict[str, object]] = []
    for _, row in fcst.iterrows():
        pred_ds_obj: object = cast(object, row["ds"])
        yhat = float(cast(SupportsFloat, row["yhat"]))
        ylo = float(cast(SupportsFloat, row["yhat_lower"]))
        yhi = float(cast(SupportsFloat, row["yhat_upper"]))
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
    logger.info(
        "[ML] Forecast upsert tenant=%s rows=%s took=%.2fs",
        business_id,
        inserted,
        time.perf_counter() - t_fc,
    )

    anomalies_summary: dict[str, object] | None = None
    if include_anomaly:
        try:
            t_an = time.perf_counter()
            iso = engine.train_anomaly_detection(ts)
            an: pd.DataFrame = engine.detect_anomalies(iso, ts)
            # keep last 30 days (sort by ds safely without pandas sort overload warnings)
            to_dict_fn: Callable[..., object] = cast(Callable[..., object], getattr(an, "to_dict"))
            recs_obj = to_dict_fn(orient="records")
            records: list[dict[str, object]] = cast(list[dict[str, object]], recs_obj) if not an.empty else []
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
            logger.info(
                "[ML] Anomaly upsert tenant=%s rows=%s took=%.2fs",
                business_id,
                a_inserted,
                time.perf_counter() - t_an,
            )
            anomalies_summary = {"inserted": a_inserted}
        except Exception as e:
            logger.warning("Anomaly pipeline failed for tenant=%s: %s", business_id, e)
            anomalies_summary = {"inserted": 0, "error": str(e)}

    total_time = time.perf_counter() - t0
    logger.info(
        "[ML] Pipeline end tenant=%s model_id=%s accuracy=%.4f forecasts=%s anomalies=%s total_time=%.2fs",
        business_id,
        saved.id,
        accuracy,
        inserted,
        anomalies_summary.get("inserted") if anomalies_summary else None,
        total_time,
    )
    return {
        "tenant_id": business_id,
        "trained": True,
        "model_id": saved.id,
        "accuracy": accuracy,
        "forecasts_inserted": inserted,
        "anomalies": anomalies_summary,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
