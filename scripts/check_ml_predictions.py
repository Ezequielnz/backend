from __future__ import annotations

import argparse
import os
import sys
from typing import Any, cast
from datetime import datetime

# Ensure 'app' package is importable when running from different CWDs
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db.supabase_client import get_supabase_service_client  # type: ignore


def main() -> None:
    parser = argparse.ArgumentParser(description="Check ml_predictions for a tenant")
    parser.add_argument("--tenant", required=True, help="Tenant (business) UUID")
    parser.add_argument("--limit", type=int, default=5, help="Rows to show per type")
    args = parser.parse_args()

    tenant_id: str = args.tenant
    limit: int = max(1, int(args.limit))

    svc = get_supabase_service_client()

    # Total rows
    total = 0
    for ptype in ("sales_forecast", "sales_anomaly"):
        resp = (
            svc.table("ml_predictions")
            .select("id")
            .eq("tenant_id", tenant_id)
            .eq("prediction_type", ptype)
            .execute()
        )
        data = cast(list[dict[str, Any]] | None, getattr(resp, "data", None)) or []
        print(f"{ptype}: {len(data)} rows")
        total += len(data)
    print(f"Total ml_predictions rows for tenant {tenant_id}: {total}")

    # Sample forecasts
    print("\nLast forecasts:")
    resp_f = (
        svc.table("ml_predictions")
        .select("id,prediction_date,predicted_values,confidence_score")
        .eq("tenant_id", tenant_id)
        .eq("prediction_type", "sales_forecast")
        .order("prediction_date", desc=True)
        .limit(limit)
        .execute()
    )
    for r in cast(list[dict[str, Any]] | None, getattr(resp_f, "data", None)) or []:
        print(r)

    print("\nLast anomalies:")
    resp_a = (
        svc.table("ml_predictions")
        .select("id,prediction_date,predicted_values,confidence_score")
        .eq("tenant_id", tenant_id)
        .eq("prediction_type", "sales_anomaly")
        .order("prediction_date", desc=True)
        .limit(limit)
        .execute()
    )
    for r in cast(list[dict[str, Any]] | None, getattr(resp_a, "data", None)) or []:
        print(r)


if __name__ == "__main__":
    main()
