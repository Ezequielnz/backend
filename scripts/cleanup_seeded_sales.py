from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta, date
from typing import Any, cast
import os
import sys

# Ensure 'app' package is importable when running from different CWDs
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db.supabase_client import get_supabase_service_client  # type: ignore

OBS_TEXT = "venta sintética (test ML)"


def _iso_utc_midnight(d: date) -> str:
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc).isoformat()


def _iso_utc_end_of_day(d: date) -> str:
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description="Cleanup seeded synthetic sales and ML artifacts for a tenant")
    parser.add_argument("--business", required=True, help="Business (tenant) UUID")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD (inclusive)")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD (inclusive)")
    parser.add_argument("--synthetic-only", dest="synthetic_only", action="store_true", default=True,
                        help=f"Delete only rows with observaciones='{OBS_TEXT}' (default: true)")
    parser.add_argument("--include-real", dest="synthetic_only", action="store_false",
                        help="Also delete real rows (NOT recommended)")
    parser.add_argument("--delete-predictions", action="store_true", default=False,
                        help="Also delete ml_predictions (sales_forecast & sales_anomaly) for this tenant and date range")
    parser.add_argument("--delete-models", action="store_true", default=False,
                        help="Also delete ml_models for this tenant (model_type='sales_forecasting')")

    args = parser.parse_args()

    tenant_id: str = args.business
    try:
        start_d = datetime.fromisoformat(args.start).date()
        end_d = datetime.fromisoformat(args.end).date()
    except ValueError:
        raise SystemExit("[ERROR] Use --start/--end con formato YYYY-MM-DD")
    if end_d < start_d:
        raise SystemExit("[ERROR] Rango de fechas inválido: end < start")

    start_iso = _iso_utc_midnight(start_d)
    end_iso = _iso_utc_end_of_day(end_d)

    svc = get_supabase_service_client()

    # 1) Delete ventas
    q = (
        svc.table("ventas")
        .select("id")
        .eq("negocio_id", tenant_id)
        .gte("fecha", start_iso)
        .lte("fecha", end_iso)
    )
    if args.synthetic_only:
        q = q.eq("observaciones", OBS_TEXT)
    pre_resp = q.execute()
    pre_rows = cast(list[dict[str, Any]] | None, getattr(pre_resp, "data", None)) or []
    print(f"ventas a eliminar: {len(pre_rows)}")

    del_q = (
        svc.table("ventas")
        .delete()
        .eq("negocio_id", tenant_id)
        .gte("fecha", start_iso)
        .lte("fecha", end_iso)
    )
    if args.synthetic_only:
        del_q = del_q.eq("observaciones", OBS_TEXT)
    del_resp = del_q.execute()
    del_rows = cast(list[dict[str, Any]] | None, getattr(del_resp, "data", None)) or []
    print(f"ventas eliminadas: {len(del_rows)}")

    # 2) Optionally delete predictions
    if args.delete_predictions:
        # Forecasts
        pf_q = (
            svc.table("ml_predictions")
            .delete()
            .eq("tenant_id", tenant_id)
            .eq("prediction_type", "sales_forecast")
            .gte("prediction_date", start_d.isoformat())
            .lte("prediction_date", end_d.isoformat())
        )
        pf_resp = pf_q.execute()
        pf_rows = cast(list[dict[str, Any]] | None, getattr(pf_resp, "data", None)) or []
        print(f"ml_predictions forecasts eliminadas: {len(pf_rows)}")

        # Anomalies
        pa_q = (
            svc.table("ml_predictions")
            .delete()
            .eq("tenant_id", tenant_id)
            .eq("prediction_type", "sales_anomaly")
            .gte("prediction_date", start_d.isoformat())
            .lte("prediction_date", end_d.isoformat())
        )
        pa_resp = pa_q.execute()
        pa_rows = cast(list[dict[str, Any]] | None, getattr(pa_resp, "data", None)) or []
        print(f"ml_predictions anomalies eliminadas: {len(pa_rows)}")

    # 3) Optionally delete models
    if args.delete_models:
        pm_q = (
            svc.table("ml_models")
            .delete()
            .eq("tenant_id", tenant_id)
            .eq("model_type", "sales_forecasting")
        )
        pm_resp = pm_q.execute()
        pm_rows = cast(list[dict[str, Any]] | None, getattr(pm_resp, "data", None)) or []
        print(f"ml_models eliminados: {len(pm_rows)}")

    print("Limpieza terminada.")


if __name__ == "__main__":
    main()
