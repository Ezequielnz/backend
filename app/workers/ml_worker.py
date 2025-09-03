"""
Worker para procesamiento de Machine Learning
"""
from app.celery_app import celery_app
from datetime import datetime, timezone
from supabase.client import create_client, Client
from app.core.config import settings
from app.core.cache_decorators import cache_ml_features, cache_ml_predictions, invalidate_on_update
from app.core.cache_manager import cache_manager
import logging
import time
import math
import numpy as np
import numbers
from typing import TYPE_CHECKING, cast, Callable, TypeVar, Protocol
from collections.abc import Mapping, Iterable
from prophet import Prophet
from billiard.exceptions import SoftTimeLimitExceeded
from app.services.ml import (
    FeatureEngineer,
    ModelVersionManager,
    train_and_predict_sales,
)

if TYPE_CHECKING:
    from celery.app.task import Task

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., object])

class _RetryingTask(Protocol):
    def retry(
        self,
        args: object | None = None,
        kwargs: object | None = None,
        exc: BaseException | None = None,
        throw: bool = True,
        eta: object | None = None,
        countdown: int | None = None,
        max_retries: int | None = None,
        **options: object,
    ) -> BaseException: ...

def task_typed(**kwargs: object) -> Callable[[F], F]:
    """
    Typed wrapper around celery_app.task to avoid 'reportUntypedFunctionDecorator' warnings.
    Keeps runtime behavior identical while providing a precise decorator type to the type checker.
    """
    task_dec = cast(Callable[..., Callable[[F], F]], celery_app.task)
    dec = task_dec(**kwargs)
    return dec

def _as_int(x: object, default: int = 0) -> int:
    """Best-effort conversion to int for values that may arrive as str/Decimal/etc.
    Returns `default` on failure or None-like values.
    """
    try:
        if x is None:
            return default
        if isinstance(x, bool):
            return 1 if x else 0
        # Accept Python ints and NumPy integer scalars (np.int64, etc.)
        if isinstance(x, numbers.Integral):
            return int(x)
        s = str(x).strip()
        if s == "" or s.lower() in ("nan", "none"):
            return default
        # allow floats encoded as string as well
        return int(float(s))
    except Exception:
        return default

def _as_float(x: object, default: float = 0.0) -> float:
    """Best-effort conversion to float for various numeric-like inputs.
    Returns `default` on failure or None-like values.
    """
    try:
        if x is None:
            return default
        if isinstance(x, bool):
            return 1.0 if x else 0.0
        # Accept Python reals and NumPy numeric scalars
        if isinstance(x, numbers.Real):
            return float(x)
        s = str(x).strip()
        if s == "":
            return default
        return float(s)
    except Exception:
        return default

def _to_iso_date(x: object) -> str:
    """
    Best-effort conversion to ISO 'YYYY-MM-DD' string from various datetime-like inputs.
    Handles datetime, objects with .date()/.isoformat(), numpy.datetime64, and scalar ndarrays.
    """
    try:
        # datetime or pandas.Timestamp (Timestamp is a datetime subclass)
        if isinstance(x, datetime):
            return x.date().isoformat()
        # numpy.datetime64
        if isinstance(x, np.datetime64):
            # Convert to ndarray with nanosecond precision, then to int64 and extract Python int
            arr_ns = np.asarray(x, dtype="datetime64[ns]")
            ns_int = cast(int, arr_ns.astype("int64").item())
            seconds = ns_int / 1_000_000_000
            return datetime.fromtimestamp(seconds, tz=timezone.utc).date().isoformat()
        # numpy scalar ndarray
        if isinstance(x, np.ndarray):
            try:
                # Try extracting scalar value; if not scalar, this raises
                return _to_iso_date(cast(object, x.item()))
            except Exception:
                return str(cast(object, x))
        # Objects exposing .date() -> date
        date_attr = getattr(x, "date", None)
        if callable(date_attr):
            d = date_attr()
            iso = getattr(d, "isoformat", None)
            if callable(iso):
                return str(iso())
        # Objects exposing .isoformat() directly
        iso = getattr(x, "isoformat", None)
        if callable(iso):
            s = iso()
            if isinstance(s, str) and len(s) >= 10 and s[4] == "-" and s[7] == "-":
                return s[:10]
        # String fallback; trim time part if present
        s = str(x)
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            return s[:10]
        return s
    except Exception:
        return str(cast(object, x))

@task_typed(bind=True, soft_time_limit=900, time_limit=1200)
def retrain_all_models(self: "Task") -> dict[str, object]:
    """
    Re-entrena todos los modelos ML (lunes 2 AM)
    """
    try:
        supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        t0 = time.perf_counter()
        logger.info("[ML] Retrain start")
        # Obtener negocios activos (usando getattr+cast para evitar Unknowns)
        sb_table = cast(Callable[[str], object], getattr(supabase, "table"))
        req = sb_table("negocios")
        req = cast(object, getattr(req, "select")("id, nombre"))
        businesses = cast(object, getattr(req, "execute")())
        biz_rows = cast(list[dict[str, object]], getattr(businesses, "data", []) or [])
        
        models_retrained = 0
        forecasts_total = 0
        anomalies_total = 0
        for business in biz_rows:
            bid = cast(str, business["id"])  # id siempre es str en nuestra tabla
            try:
                tb = time.perf_counter()
                result = train_and_predict_sales(bid, horizon_days=14, history_days=365)
                if result.get("trained"):
                    models_retrained += 1
                forecasts_total += _as_int(result.get("forecasts_inserted", 0), 0)
                an_raw = result.get("anomalies")
                inserted_anoms = 0
                if isinstance(an_raw, dict):
                    an_dict = cast(dict[str, object], an_raw)
                    inserted_anoms = _as_int(an_dict.get("inserted", 0), 0)
                anomalies_total += inserted_anoms
                logger.info(
                    f"ML retrain completed for negocio={business['nombre']} (forecasts={result.get('forecasts_inserted')}, accuracy={result.get('accuracy')}, took={time.perf_counter()-tb:.2f}s)"
                )
            except Exception as ie:
                logger.error(f"Error retraining tenant={bid}: {ie}")
                continue

        elapsed = time.perf_counter() - t0
        logger.info(
            "[ML] Retrain end businesses=%s models=%s forecasts=%s anomalies=%s took=%.2fs",
            len(biz_rows),
            models_retrained,
            forecasts_total,
            anomalies_total,
            elapsed,
        )
        return {
            "task": "retrain_all_models",
            "businesses_processed": len(biz_rows),
            "models_retrained": models_retrained,
            "forecasts_inserted": forecasts_total,
            "anomalies_inserted": anomalies_total,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
    except SoftTimeLimitExceeded as e:
        logger.error(f"Soft time limit exceeded in retrain_all_models: {e}")
        raise
    except Exception as e:
        logger.error(f"Error en re-entrenamiento: {str(e)}")
        raise cast(_RetryingTask, self).retry(exc=e, countdown=300, max_retries=2)

@task_typed(bind=True, soft_time_limit=600, time_limit=900)
@invalidate_on_update('ml_features')
def update_business_features(self: "Task") -> dict[str, object]:
    """
    Actualiza features ML cada hora
    """
    try:
        supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        t0 = time.perf_counter()
        # Obtener negocios activos (usando getattr+cast para evitar Unknowns)
        sb_table = cast(Callable[[str], object], getattr(supabase, "table"))
        req = sb_table("negocios")
        req = cast(object, getattr(req, "select")("id, nombre"))
        businesses = cast(object, getattr(req, "execute")())
        biz_rows = cast(list[dict[str, object]], getattr(businesses, "data", []) or [])

        fe = FeatureEngineer()
        features_updated = 0
        for business in biz_rows:
            bid = cast(str, business["id"])  # id es str
            try:
                # Sales metrics (last 30 days)
                t_bus = time.perf_counter()
                ts = fe.sales_timeseries_daily(bid, days=90)
                if not ts.empty:
                    upserted = fe.persist_sales_features(bid, ts.tail(30))
                    features_updated += int(upserted)
                # Inventory metrics snapshot (today)
                inv = fe.inventory_snapshot(bid)
                fe.persist_inventory_features(bid, inv)
                features_updated += 1
                # Invalidate cached feature keys for this tenant (pattern)
                cache_manager.invalidate_pattern(f"ml_features:features_{bid}")
                logger.info(
                    f"Features actualizadas para negocio: {business['nombre']} (took={time.perf_counter()-t_bus:.2f}s)"
                )
            except Exception as ie:
                logger.error(f"Error updating features for tenant={bid}: {ie}")
                continue

        logger.info("[ML] update_business_features end businesses=%s updated=%s took=%.2fs", len(biz_rows), features_updated, time.perf_counter()-t0)
        return {
            "task": "update_business_features",
            "businesses_processed": len(biz_rows),
            "features_updated": features_updated,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
    except SoftTimeLimitExceeded as e:
        logger.error(f"Soft time limit exceeded in update_business_features: {e}")
        raise
    except Exception as e:
        logger.error(f"Error actualizando features: {str(e)}")
        raise cast(_RetryingTask, self).retry(exc=e, countdown=60, max_retries=3)

@task_typed(bind=True, soft_time_limit=300, time_limit=600)
@cache_ml_predictions(ttl=1800)
def generate_predictions(self: "Task", business_id: str, prediction_type: str) -> dict[str, object]:
    """
    Genera predicciones ML para un negocio específico
    """
    try:
        supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        t0 = time.perf_counter()

        # Try to use existing active model; if not present, train pipeline once
        store = ModelVersionManager()
        model = store.load_active_model(business_id, model_type="sales_forecasting")
        if model is None:
            result = train_and_predict_sales(business_id, horizon_days=14, history_days=365)
            logger.info(
                f"Predicciones generadas via pipeline inicial tenant={business_id} forecasts={result.get('forecasts_inserted')}"
            )
            return {
                "task": "generate_predictions",
                "business_id": business_id,
                "prediction_type": prediction_type,
                "pipeline_trained": result.get("trained"),
                "forecasts_inserted": result.get("forecasts_inserted"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        # If we have a model, generate according to requested type
        from app.services.ml import BusinessMLEngine, FeatureEngineer  # local import to avoid cyclical
        engine = BusinessMLEngine()
        fe = FeatureEngineer()
        # Fetch active model_id once for reuse
        # Query model id con getattr+cast para evitar Partial Unknowns
        sb_table = cast(Callable[[str], object], getattr(supabase, "table"))
        req = sb_table("ml_models")
        req = cast(object, getattr(req, "select")("id"))
        req = cast(object, getattr(req, "eq")("tenant_id", business_id))
        req = cast(object, getattr(req, "eq")("is_active", True))
        req = cast(object, getattr(req, "limit")(1))
        mid_resp = cast(object, getattr(req, "execute")())
        mid_rows = cast(list[dict[str, object]], getattr(mid_resp, "data", []) or [])
        model_id = cast(str, mid_rows[0]["id"]) if mid_rows else None
        inserted = 0
        if prediction_type == "sales_forecast":
            fcst = engine.forecast_sales(cast(Prophet, model), horizon_days=14)
            if model_id is None:
                logger.warning(f"No active model_id found for tenant={business_id}; skipping forecast upsert")
            else:
                forecast_payloads: list[dict[str, object]] = []
                for _, row in fcst.iterrows():
                    row_obj = cast(object, row)
                    row_map = cast(Mapping[str, object], row_obj)
                    ds_obj = row_map["ds"]
                    yhat = _as_float(row_map.get("yhat"))
                    yhat_lower = _as_float(row_map.get("yhat_lower"))
                    yhat_upper = _as_float(row_map.get("yhat_upper"))
                    forecast_payloads.append(
                        {
                            "tenant_id": business_id,
                            "model_id": model_id,
                            "prediction_date": _to_iso_date(ds_obj),
                            "prediction_type": "sales_forecast",
                            "predicted_values": {
                                "yhat": yhat,
                                "yhat_lower": yhat_lower,
                                "yhat_upper": yhat_upper,
                            },
                            # Simple confidence from interval width
                            "confidence_score": float(
                                max(
                                    0.0,
                                    min(
                                        1.0,
                                        1.0 / (1.0 + abs(yhat_upper - yhat_lower) / max(abs(yhat), 1e-6)),
                                    ),
                                )
                            ),
                        }
                    )
                if forecast_payloads:
                    chunk = 200
                    for i in range(0, len(forecast_payloads), chunk):
                        sb_table = cast(Callable[[str], object], getattr(supabase, "table"))
                        tbl = sb_table("ml_predictions")
                        up = cast(object, getattr(tbl, "upsert")(forecast_payloads[i : i + chunk], on_conflict="tenant_id,prediction_date,prediction_type"))
                        getattr(up, "execute")()
                    inserted = len(forecast_payloads)
        elif prediction_type == "sales_anomaly":
            ts = fe.sales_timeseries_daily(business_id, days=120)
            if not ts.empty:
                iso = engine.train_anomaly_detection(ts)
                # Build a typed view without using Any
                an0 = cast(object, engine.detect_anomalies(iso, ts))
                an_sorted = cast(object, getattr(an0, "sort_values")("ds"))
                an_tail = cast(object, getattr(an_sorted, "iloc")[-30:])
                if model_id is None:
                    logger.warning(f"No active model_id found for tenant={business_id}; skipping anomaly upsert")
                else:
                    anomaly_payloads: list[dict[str, object]] = []
                    it = cast(Callable[[], Iterable[tuple[object, object]]], getattr(an_tail, "iterrows"))
                    for _, r_raw in it():
                        r = cast(Mapping[str, object], r_raw)
                        is_anom = bool(r.get("is_anomaly", False))
                        if is_anom:
                            ds_obj = r["ds"]
                            y_val = _as_float(r.get("y"))
                            score_val = _as_float(r.get("score", 0.0))
                            anomaly_payloads.append(
                                {
                                    "tenant_id": business_id,
                                    "model_id": model_id,
                                    "prediction_date": _to_iso_date(ds_obj),
                                    "prediction_type": "sales_anomaly",
                                    "predicted_values": {
                                        "y": y_val,
                                        "score": score_val,
                                        "is_anomaly": True,
                                    },
                                    "confidence_score": float(1.0 / (1.0 + math.exp(5.0 * score_val))),
                                }
                            )
                    if anomaly_payloads:
                        chunk = 200
                        for i in range(0, len(anomaly_payloads), chunk):
                            sb_table = cast(Callable[[str], object], getattr(supabase, "table"))
                            tbl = sb_table("ml_predictions")
                            up = cast(object, getattr(tbl, "upsert")(anomaly_payloads[i : i + chunk], on_conflict="tenant_id,prediction_date,prediction_type"))
                            getattr(up, "execute")()
                        inserted = len(anomaly_payloads)

        logger.info(
            f"Predicción generada: {prediction_type} para negocio {business_id} (rows={inserted}, took={time.perf_counter()-t0:.2f}s)"
        )

        return {
            "task": "generate_predictions",
            "business_id": business_id,
            "prediction_type": prediction_type,
            "rows": inserted,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
    except SoftTimeLimitExceeded as e:
        logger.error(f"Soft time limit exceeded in generate_predictions: {e}")
        raise
    except Exception as e:
        logger.error(f"Error generando predicción: {str(e)}")
        raise cast(_RetryingTask, self).retry(exc=e, countdown=60, max_retries=3)

@task_typed(bind=True, soft_time_limit=300, time_limit=600)
@cache_ml_features(ttl=3600)
def analyze_business_trends(self: "Task", business_id: str) -> dict[str, object]:
    """
    Analiza tendencias de negocio
    """
    try:
        supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        t0 = time.perf_counter()
        # Obtener datos del negocio
        sb_table = cast(Callable[[str], object], getattr(supabase, "table"))
        req = sb_table("negocios")
        req = cast(object, getattr(req, "select")("*"))
        req = cast(object, getattr(req, "eq")("id", business_id))
        req = cast(object, getattr(req, "single")())
        business = cast(object, getattr(req, "execute")())
        business_data = cast(dict[str, object] | None, getattr(business, "data", None))
        
        if not business_data:
            raise ValueError(f"Negocio {business_id} no encontrado")
        
        # Simular análisis de tendencias
        trends = {
            "sales_growth": float(np.random.uniform(-0.1, 0.3)),
            "customer_retention": float(np.random.uniform(0.6, 0.9)),
            "inventory_turnover": float(np.random.uniform(2, 8)),
            "profit_margin": float(np.random.uniform(0.1, 0.4)),
        }
        
        logger.info(
            f"Análisis de tendencias completado para negocio: {business_data['nombre']} (took={time.perf_counter()-t0:.2f}s)"
        )
        
        return {
            "task": "analyze_business_trends",
            "business_id": business_id,
            "business_name": cast(str, business_data["nombre"]),
            "trends": trends,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except SoftTimeLimitExceeded as e:
        logger.error(f"Soft time limit exceeded in analyze_business_trends: {e}")
        raise
    except Exception as e:
        logger.error(f"Error analizando tendencias: {str(e)}")
        raise cast(_RetryingTask, self).retry(exc=e, countdown=60, max_retries=3)
