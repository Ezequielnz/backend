from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, date
from typing import Any, Callable, cast, Protocol

import numpy as np
import os
import sys
import importlib

# Project imports
## Ensure 'app' package is importable when running from different CWDs
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    class APIResponseProto(Protocol):
        @property
        def data(self) -> list[dict[str, object]] | None: ...

    class TableQueryProto(Protocol):
        def select(self, columns: str) -> "TableQueryProto": ...
        def eq(self, column: str, value: object) -> "TableQueryProto": ...
        def gte(self, column: str, value: object) -> "TableQueryProto": ...
        def lte(self, column: str, value: object) -> "TableQueryProto": ...
        def order(self, column: str, desc: bool = False) -> "TableQueryProto": ...
        def limit(self, n: int) -> "TableQueryProto": ...
        def insert(self, data: object, *, count: object | None = None, returning: object | None = None, upsert: bool = False) -> "TableQueryProto": ...
        def execute(self) -> "APIResponseProto": ...
else:
    # Runtime fallbacks to avoid import errors if types aren't available
    TableQueryProto = object  # type: ignore[assignment]
    APIResponseProto = object  # type: ignore[assignment]


def _to_iso_date_str(x: object) -> str:
    if isinstance(x, datetime):
        return x.date().isoformat()
    if isinstance(x, date):
        return x.isoformat()
    s = str(x).strip()
    if "T" in s:
        return s.split("T")[0]
    if " " in s:
        return s.split(" ")[0]
    return s[:10]


def _iso_utc_midnight(d: date) -> str:
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc).isoformat()


def _get_table(svc: object, name: str) -> TableQueryProto:
    table_fn: Callable[[str], object] = cast(Callable[[str], object], getattr(svc, "table"))
    return cast(TableQueryProto, table_fn(name))


def validate_business_exists(svc: object, business_id: str) -> bool:
    resp: APIResponseProto = _get_table(svc, "negocios").select("id").eq("id", business_id).limit(1).execute()
    data = cast(list[dict[str, Any]] | None, getattr(resp, "data", None))
    return bool(data)


def fetch_existing_days(svc: object, business_id: str, start: date, end: date) -> set[str]:
    tbl = _get_table(svc, "ventas")
    resp: APIResponseProto = (
        tbl.select("fecha")
        .eq("negocio_id", business_id)
        .gte("fecha", start.isoformat())
        .lte("fecha", (end + timedelta(days=1)).isoformat())
        .order("fecha")
        .execute()
    )
    rows = cast(list[dict[str, Any]] | None, getattr(resp, "data", None)) or []
    days: set[str] = set()
    for r in rows:
        f = str(r.get("fecha", "")).strip()
        days.add(_to_iso_date_str(f))
    return days


def get_any_usuario_negocio_id(svc: object, business_id: str) -> str | None:
    """
    Try to fetch a valid usuario_negocio link id for a business.
    Handles both possible table names: 'usuarios_negocios' and 'negocio_usuarios'.
    Returns the id as string or None if not found.
    """
    table_names = ("usuarios_negocios", "negocio_usuarios")
    for tname in table_names:
        try:
            resp: APIResponseProto = (
                _get_table(svc, tname).select("id").eq("negocio_id", business_id).limit(1).execute()
            )
            rows = cast(list[dict[str, Any]] | None, getattr(resp, "data", None)) or []
            if rows and rows[0].get("id"):
                return str(rows[0]["id"])
        except Exception:
            # ignore and try next table name
            pass
    return None


@dataclass(frozen=True)
class AnomalyPlan:
    high_idx: int
    low_idx: int


def generate_daily_series(days: int, *, base_mean: float = 100.0, rel_noise: float = 0.2,
                           weekend_mult_low: float = 1.2, weekend_mult_high: float = 1.5,
                           include_anomalies: bool = True, seed: int | None = None) -> tuple[list[date], list[float], AnomalyPlan | None]:
    rng = np.random.default_rng(seed)
    today = datetime.now(timezone.utc).date()
    dates = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    values: list[float] = []
    for d in dates:
        noise = float(rng.normal(0.0, rel_noise))
        base = max(1.0, base_mean * (1.0 + noise))
        if d.weekday() >= 5:  # 5=Sat,6=Sun
            base *= float(rng.uniform(weekend_mult_low, weekend_mult_high))
        values.append(round(max(1.0, base), 2))

    plan: AnomalyPlan | None = None
    if include_anomalies and days >= 2:
        hi_idx = days // 3
        lo_idx = (2 * days) // 3
        # Ensure distinct
        if hi_idx == lo_idx:
            lo_idx = min(days - 1, hi_idx + 1)
        # Apply
        values[hi_idx] = round(max(1.0, values[hi_idx] * 3.5), 2)   # spike
        values[lo_idx] = round(max(1.0, values[lo_idx] * 0.3), 2)   # drop
        plan = AnomalyPlan(high_idx=hi_idx, low_idx=lo_idx)
    return dates, values, plan


def build_payloads(business_id: str, dates: list[date], values: list[float], medio_pago: str,
                   observation_prefix: str = "venta sintética (test ML)",
                   usuario_negocio_id: str | None = None) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for d, v in zip(dates, values):
        payloads.append({
            "negocio_id": business_id,
            "cliente_id": None,
            "usuario_negocio_id": usuario_negocio_id,
            "medio_pago": medio_pago,
            "total": float(round(v, 2)),
            "fecha": _iso_utc_midnight(d),
            "observaciones": observation_prefix,
        })
    return payloads


def insert_in_batches(svc: object, table: str, rows: list[dict[str, Any]], chunk: int = 200) -> int:
    if not rows:
        return 0
    total = 0
    for i in range(0, len(rows), chunk):
        _ = _get_table(svc, table).insert(rows[i:i + chunk]).execute()
        total += len(rows[i:i + chunk])
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed synthetic daily sales timeseries for a business")
    parser.add_argument("--business", required=True, help="Business (negocio) UUID")
    parser.add_argument("--days", type=int, default=90, help="Number of days to generate (default: 90)")
    parser.add_argument("--medio-pago", choices=["efectivo", "tarjeta", "transferencia"], default="efectivo")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument("--no-anomalies", dest="anomalies", action="store_false", help="Disable anomalies")
    parser.add_argument("--no-skip-existing", dest="skip_existing", action="store_false", help="Do not skip days that already have sales (may duplicate totals)")
    parser.add_argument("--dry-run", action="store_true", help="Only print plan, do not insert")
    parser.add_argument("--no-run-ml", dest="run_ml", action="store_false", help="Do not run ML pipeline after seeding")

    parser.set_defaults(anomalies=True, skip_existing=True, run_ml=True)
    args = parser.parse_args()

    business_id: str = args.business
    days: int = max(1, int(args.days))
    medio_pago: str = args.medio_pago

    # Import service client dynamically to avoid top-level import issues
    supabase_mod = importlib.import_module("app.db.supabase_client")
    get_supabase_service_client = getattr(supabase_mod, "get_supabase_service_client")
    svc = get_supabase_service_client()

    # Validate business
    if not validate_business_exists(svc, business_id):
        raise SystemExit(f"[ERROR] negocio_id no existe: {business_id}")

    # Generate series
    dates, values, plan = generate_daily_series(
        days,
        include_anomalies=bool(args.anomalies),
        seed=args.seed,
    )

    start, end = dates[0], dates[-1]

    # Skip days that already have sales to avoid double counting
    existing_days: set[str] = set()
    if bool(args.skip_existing):
        existing_days = fetch_existing_days(svc, business_id, start, end)

    # Pick an existing usuarios_negocios link if present (some schemas enforce FK)
    usuario_negocio_id = get_any_usuario_negocio_id(svc, business_id)

    payloads = build_payloads(business_id, dates, values, medio_pago, usuario_negocio_id=usuario_negocio_id)
    if existing_days:
        payloads = [p for p in payloads if _to_iso_date_str(p["fecha"]) not in existing_days]

    print("=== Seed Plan ===")
    print(f"Business: {business_id}")
    print(f"Days requested: {days}")
    print(f"Date range: {start.isoformat()} -> {end.isoformat()}")
    print(f"Medio pago: {medio_pago}")
    print(f"Anomalies: {'yes' if args.anomalies else 'no'}")
    if plan is not None:
        hi_d = dates[plan.high_idx]
        lo_d = dates[plan.low_idx]
        print(f"  - High spike at index {plan.high_idx} ({hi_d.isoformat()})")
        print(f"  - Low drop at index {plan.low_idx} ({lo_d.isoformat()})")
    print(f"Skip existing days: {'yes' if args.skip_existing else 'no'}")
    print(f"Existing days in range (detected): {len(existing_days)}")
    print(f"Rows to insert: {len(payloads)}")

    if args.dry_run:
        print("[DRY RUN] No se inserta nada.")
        return

    inserted = insert_in_batches(svc, "ventas", payloads)
    print(f"Inserted rows: {inserted}")

    if bool(args.run_ml):
        print("[ML] Running training and prediction pipeline...")
        ml_mod = importlib.import_module("app.services.ml.pipeline")
        train_and_predict_sales = getattr(ml_mod, "train_and_predict_sales")
        res = train_and_predict_sales(
            business_id=business_id,
            horizon_days=14,
            history_days=max(30, days),
            include_anomaly=True,
            model_version="1.0",
        )
        print("[ML] Result:")
        print({k: res.get(k) for k in ["trained", "model_id", "accuracy", "forecasts_inserted", "anomalies", "timestamp"]})


if __name__ == "__main__":
    main()
