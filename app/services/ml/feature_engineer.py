from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import cast, Callable

import pandas as pd
import numpy as np
from numpy.typing import NDArray

from app.core.cache_decorators import cached
from app.db.supabase_client import (
    TableQueryProto,
    APIResponseProto,
    get_supabase_service_client,
)

_logger = logging.getLogger(__name__)


def _to_iso_date_str(x: object) -> str:
    """Convert date-like objects to 'YYYY-MM-DD' safely for JSON serialization."""
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


def _as_float(x: object, default: float = 0.0) -> float:
    """Best-effort conversion to float for numbers that may arrive as str/Decimal/etc.
    Returns `default` on failure or None-like values.
    """
    try:
        if x is None:
            return default
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip()
        if s == "" or s.lower() in ("nan", "none"):
            return default
        return float(s)
    except Exception:
        return default


def _as_int(x: object, default: int = 0) -> int:
    """Best-effort conversion to int for values that may arrive as str/Decimal/etc."""
    try:
        if x is None:
            return default
        if isinstance(x, bool):
            return 1 if x else 0
        if isinstance(x, int):
            return x
        if isinstance(x, np.integer):
            # Use .item() to obtain a Python int
            return x.item()
        s = str(x).strip()
        if s == "" or s.lower() in ("nan", "none"):
            return default
        # allow floats encoded as string as well
        return int(float(s))
    except Exception:
        return default

# -----------------------------
# Pandas typing-safe helpers
# -----------------------------
def _to_datetime_series(values: object, errors: str = "coerce") -> pd.Series:
    """Typed wrapper around pandas.to_datetime returning a Series.
    Uses getattr to avoid overload signature issues in stubs.
    """
    to_dt_any: Callable[..., object] = cast(Callable[..., object], getattr(pd, "to_datetime"))
    return cast(pd.Series, to_dt_any(values, errors=errors))


def _to_numeric_series(values: object, errors: str = "coerce") -> pd.Series:
    """Typed wrapper around pandas.to_numeric returning a Series."""
    to_num_any: Callable[..., object] = cast(Callable[..., object], getattr(pd, "to_numeric"))
    return cast(pd.Series, to_num_any(values, errors=errors))


def _series_dt_date(series: pd.Series) -> pd.Series:
    """Return python date objects from a datetime-like Series using the dt accessor."""
    dt_any: object = cast(object, getattr(series, "dt"))
    return cast(pd.Series, getattr(dt_any, "date"))


def _series_fillna(series: pd.Series, value: float) -> pd.Series:
    fillna_any: Callable[..., object] = cast(Callable[..., object], getattr(series, "fillna"))
    return cast(pd.Series, fillna_any(value))


def _groupby_sum(df: pd.DataFrame, by: str, value_col: str) -> pd.DataFrame:
    """Group by `by` and sum `value_col`, returning a DataFrame with columns [by, value_col]."""
    groupby_any: Callable[..., object] = cast(Callable[..., object], getattr(df, "groupby"))
    gb_obj = groupby_any(by, as_index=False)
    # Select the value column and sum
    getitem_any: Callable[[str], object] = cast(Callable[[str], object], getattr(gb_obj, "__getitem__"))
    y_selector = getitem_any(value_col)
    sum_any: Callable[..., object] = cast(Callable[..., object], getattr(y_selector, "sum"))
    return cast(pd.DataFrame, sum_any())


def _set_index_reindex_rename_reset(
    df: pd.DataFrame, index_col: str, new_index: pd.Index, index_name: str, fill_value: float = 0.0
) -> pd.DataFrame:
    """Chain set_index -> reindex -> rename_axis -> reset_index with typed wrappers."""
    set_index_any: Callable[..., object] = cast(Callable[..., object], getattr(df, "set_index"))
    df2 = set_index_any(index_col)
    reindex_any: Callable[..., object] = cast(Callable[..., object], getattr(df2, "reindex"))
    df3 = reindex_any(new_index, fill_value=fill_value)
    rename_axis_any: Callable[..., object] = cast(Callable[..., object], getattr(df3, "rename_axis"))
    df4 = rename_axis_any(index_name)
    reset_index_any: Callable[..., object] = cast(Callable[..., object], getattr(df4, "reset_index"))
    return cast(pd.DataFrame, reset_index_any())


def _series_min_max(series: pd.Series) -> tuple[pd.Timestamp, pd.Timestamp]:
    min_fn: Callable[[], object] = cast(Callable[[], object], getattr(series, "min"))
    max_fn: Callable[[], object] = cast(Callable[[], object], getattr(series, "max"))
    return cast(pd.Timestamp, min_fn()), cast(pd.Timestamp, max_fn())


def _date_range(start: pd.Timestamp, end: pd.Timestamp, freq: str = "D") -> pd.DatetimeIndex:
    date_range_any: Callable[..., object] = cast(Callable[..., object], getattr(pd, "date_range"))
    return cast(pd.DatetimeIndex, date_range_any(start, end, freq=freq))


def _df_col(df: pd.DataFrame, col: str) -> pd.Series:
    """Typed access to a DataFrame column as Series."""
    getitem_any: Callable[[str], object] = cast(Callable[[str], object], getattr(df, "__getitem__"))
    return cast(pd.Series, getitem_any(col))


def _series_isna_all(series: pd.Series) -> bool:
    isna_any: Callable[[], object] = cast(Callable[[], object], getattr(series, "isna"))
    isna_series = cast(pd.Series, isna_any())
    all_any: Callable[[], object] = cast(Callable[[], object], getattr(isna_series, "all"))
    return bool(all_any())

@dataclass(frozen=True)
class TimeRange:
    start: date
    end: date

    @staticmethod
    def last_days(days: int) -> "TimeRange":
        today = datetime.now(timezone.utc).date()
        return TimeRange(start=today - timedelta(days=days - 1), end=today)


class FeatureEngineer:
    """
    Extracts domain features for ML from ERP data (ventas, compras, productos, etc.).
    All reads use the Supabase Service client as these tasks run server-side (Celery) and may bypass RLS.
    Persisted features are stored in `ml_features` using upserts per (tenant_id, feature_date, feature_type).
    """

    def __init__(self) -> None:
        super().__init__()
        # Store supabase service client as opaque object to avoid leaking Unknown types
        self.client: object = get_supabase_service_client()

    def _table(self, name: str) -> TableQueryProto:
        """Typed access to Supabase table to avoid unknown member warnings."""
        table_fn: Callable[[str], object] = cast(Callable[[str], object], getattr(self.client, "table"))
        return cast(TableQueryProto, table_fn(name))

    # -----------------------------
    # Sales features
    # -----------------------------
    def get_sales_rows(
        self, business_id: str, timerange: TimeRange | None = None
    ) -> list[dict[str, object]]:
        """
        Fetch raw `ventas` rows for a tenant and optional date range.
        Columns used: id, negocio_id, fecha (timestamp with tz), total (numeric)
        """
        query: TableQueryProto = self._table("ventas").select("id,negocio_id,fecha,total")
        query = query.eq("negocio_id", business_id)
        if timerange is not None:
            # use ISO strings for filters
            query = query.gte("fecha", timerange.start.isoformat())
            query = query.lte("fecha", (timerange.end + timedelta(days=1)).isoformat())
        resp: APIResponseProto = query.order("fecha").execute()
        data_list = cast(list[dict[str, object]] | None, getattr(resp, "data", None))
        rows: list[dict[str, object]] = data_list if data_list is not None else []
        _logger.debug("[FE] ventas rows tenant=%s count=%s", business_id, len(rows))
        return rows

    def sales_timeseries_daily(
        self, business_id: str, days: int = 365
    ) -> pd.DataFrame:
        """
        Returns a daily time series with columns [ds (date), y (float)] summing totals per day.
        """
        # Guard against invalid day ranges
        if days < 1:
            days = 1
        timerange = TimeRange.last_days(days)
        rows = self.get_sales_rows(business_id, timerange)
        if not rows:
            return pd.DataFrame({"ds": pd.Series(dtype="object"), "y": pd.Series(dtype="float")})
        df: pd.DataFrame = pd.DataFrame(rows)
        # Normalize fecha -> date
        fecha_series: pd.Series = _to_datetime_series(_df_col(df, "fecha"), errors="coerce")
        df.loc[:, "fecha"] = fecha_series
        df = df.dropna(subset=["fecha"])  # remove invalid
        if df.empty:
            return pd.DataFrame({"ds": pd.Series(dtype="object"), "y": pd.Series(dtype="float")})
        # Use helper to avoid dt typing warnings
        ds_series: pd.Series = _series_dt_date(fecha_series)
        df.loc[:, "ds"] = ds_series
        # total may come as Decimal/str -> float
        y_num: pd.Series = _to_numeric_series(_df_col(df, "total"), errors="coerce")
        y_num_filled: pd.Series = _series_fillna(y_num, 0.0)
        df.loc[:, "y"] = y_num_filled
        grp: pd.DataFrame = _groupby_sum(df, "ds", "y")
        # Ensure continuous date index (fill missing days with 0)
        grp.loc[:, "ds"] = _to_datetime_series(_df_col(grp, "ds"), errors="coerce")
        # If all dates are NaT after coercion, return an empty frame (typed-safe boolean)
        if _series_isna_all(_df_col(grp, "ds")):
            return pd.DataFrame({"ds": pd.Series(dtype="object"), "y": pd.Series(dtype="float")})
        start_dt, end_dt = _series_min_max(_df_col(grp, "ds"))
        full_idx = _date_range(start_dt, end_dt, freq="D")
        grp = _set_index_reindex_rename_reset(grp, "ds", full_idx, "ds", fill_value=0.0)
        # Convert back to date objects for downstream compatibility
        grp.loc[:, "ds"] = _series_dt_date(_to_datetime_series(_df_col(grp, "ds"), errors="coerce"))
        return grp  # columns: ds (date), y (float)

    def persist_sales_features(self, business_id: str, daily_ts: pd.DataFrame) -> int:
        """
        Persist simple daily sales metrics into `ml_features` with feature_type = 'sales_metrics'.
        For each day, store { daily_total, moving_avg_7, moving_avg_28 }.
        Returns number of rows upserted.
        """
        if daily_ts.empty:
            return 0
        # moving averages
        tmp = daily_ts.copy()
        # Typed sort_values
        sort_values_any: Callable[..., object] = cast(Callable[..., object], getattr(tmp, "sort_values"))
        tmp = cast(pd.DataFrame, sort_values_any("ds"))
        # Typed rolling mean calculations
        y_series: pd.Series = _df_col(tmp, "y")
        rolling_any: Callable[..., object] = cast(Callable[..., object], getattr(y_series, "rolling"))
        roll7 = rolling_any(window=7, min_periods=1)
        mean_any: Callable[..., object] = cast(Callable[..., object], getattr(roll7, "mean"))
        ma7_series: pd.Series = cast(pd.Series, mean_any())
        tmp.loc[:, "ma7"] = ma7_series
        roll28 = rolling_any(window=28, min_periods=1)
        mean_any2: Callable[..., object] = cast(Callable[..., object], getattr(roll28, "mean"))
        ma28_series: pd.Series = cast(pd.Series, mean_any2())
        tmp.loc[:, "ma28"] = ma28_series
        # Build payloads and batch upsert to reduce network round-trips
        payloads: list[dict[str, object]] = []
        # basedpyright note: pandas stubs may not expose the 'orient' overload; call via getattr to avoid signature checking
        records_df: pd.DataFrame = cast(pd.DataFrame, tmp[["ds", "y", "ma7", "ma28"]])
        to_dict_any: Callable[..., object] = cast(Callable[..., object], getattr(records_df, "to_dict"))
        records: list[dict[str, object]] = cast(list[dict[str, object]], to_dict_any(orient="records"))
        for rec in records:
            feature_date_str = _to_iso_date_str(rec.get("ds", ""))
            payloads.append(
                {
                    "tenant_id": business_id,
                    "feature_date": feature_date_str,
                    "feature_type": "sales_metrics",
                    "features": {
                        "daily_total": _as_float(rec.get("y", 0.0)),
                        "ma7": _as_float(rec.get("ma7", 0.0)),
                        "ma28": _as_float(rec.get("ma28", 0.0)),
                    },
                    "metadata": {"source": "feature_engineer"},
                }
            )
        if not payloads:
            return 0
        chunk = 200
        for i in range(0, len(payloads), chunk):
            _ = self._table("ml_features").upsert(
                payloads[i : i + chunk], on_conflict="tenant_id,feature_date,feature_type"
            ).execute()
        return len(payloads)

    # -----------------------------
    # Inventory features
    # -----------------------------
    def inventory_snapshot(self, business_id: str) -> dict[str, object]:
        """
        Compute simple inventory metrics from `productos`.
        Columns used: id, negocio_id, activo, stock_actual, precio_compra (optional)
        """
        resp: APIResponseProto = (
            self._table("productos")
            .select("id,negocio_id,activo,stock_actual,precio_compra")
            .eq("negocio_id", business_id)
            .execute()
        )
        data_list = cast(list[dict[str, object]] | None, getattr(resp, "data", None))
        rows: list[dict[str, object]] = data_list if data_list is not None else []
        if not rows:
            return {
                "total_items": 0,
                "active_items": 0,
                "total_stock_units": 0,
                "avg_stock_per_item": 0.0,
            }
        df: pd.DataFrame = pd.DataFrame(rows)
        # Normalize columns to expected types
        act_series: pd.Series = _df_col(df, "activo")
        fillna_any2: Callable[..., object] = cast(Callable[..., object], getattr(act_series, "fillna"))
        act_filled: pd.Series = cast(pd.Series, fillna_any2(True))
        astype_any3: Callable[..., object] = cast(Callable[..., object], getattr(act_filled, "astype"))
        act_bool_series: pd.Series = cast(pd.Series, astype_any3(bool))
        df.loc[:, "activo"] = act_bool_series

        stock_series0: pd.Series = _df_col(df, "stock_actual")
        stock_num: pd.Series = _to_numeric_series(stock_series0, errors="coerce")
        stock_num_filled: pd.Series = _series_fillna(stock_num, 0.0)
        astype_any4: Callable[..., object] = cast(Callable[..., object], getattr(stock_num_filled, "astype"))
        stock_int_series: pd.Series = cast(pd.Series, astype_any4(int))
        df.loc[:, "stock_actual"] = stock_int_series
        total_items = len(df)
        act_series2: pd.Series = _df_col(df, "activo")
        astype_any5: Callable[..., object] = cast(Callable[..., object], getattr(act_series2, "astype"))
        act_bool2: pd.Series = cast(pd.Series, astype_any5(bool))
        to_numpy_any1: Callable[..., object] = cast(Callable[..., object], getattr(act_bool2, "to_numpy"))
        active_bool_np: NDArray[np.bool_] = cast(NDArray[np.bool_], to_numpy_any1(dtype=bool))
        sum_active_any: Callable[..., object] = cast(Callable[..., object], getattr(active_bool_np, "sum"))
        active_items = _as_int(sum_active_any(), 0)
        stock_series2: pd.Series = _df_col(df, "stock_actual")
        to_numpy_any2: Callable[..., object] = cast(Callable[..., object], getattr(stock_series2, "to_numpy"))
        stock_np: NDArray[np.int64] = cast(NDArray[np.int64], to_numpy_any2(dtype=int))
        sum_stock_any: Callable[..., object] = cast(Callable[..., object], getattr(stock_np, "sum"))
        total_stock_units = _as_int(sum_stock_any(), 0)
        mean_stock_any: Callable[..., object] = cast(Callable[..., object], getattr(stock_np, "mean"))
        avg_stock_per_item = _as_float(mean_stock_any(), 0.0) if total_items > 0 else 0.0
        return {
            "total_items": total_items,
            "active_items": active_items,
            "total_stock_units": total_stock_units,
            "avg_stock_per_item": avg_stock_per_item,
        }

    def persist_inventory_features(self, business_id: str, snapshot: dict[str, object]) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        payload: dict[str, object] = {
            "tenant_id": business_id,
            "feature_date": today,
            "feature_type": "inventory_metrics",
            "features": snapshot,
            "metadata": {"source": "feature_engineer"},
        }
        _ = self._table("ml_features").upsert(
            payload, on_conflict="tenant_id,feature_date,feature_type"
        ).execute()


# Lightweight cached accessor for sales time series
def _sales_ts_key(*args: object, **kwargs: object) -> str:
    # args for unbound function: (business_id, days)
    bid = str(args[0]) if args else str(kwargs.get("business_id", "unknown"))
    raw_days_obj: object = args[1] if len(args) > 1 else kwargs.get("days", 365)
    d_raw = _as_int(raw_days_obj, 365)
    d = d_raw if d_raw >= 1 else 1
    # Use features_{bid}_... so pattern invalidation on features_{bid} works
    return f"features_{bid}_sales_timeseries_{d}"

@cached("ml_features", ttl=1800, key_func=_sales_ts_key)
def get_sales_timeseries_cached(business_id: str, days: int = 365) -> list[dict[str, object]]:
    fe = FeatureEngineer()
    d = days if days >= 1 else 1
    ts = fe.sales_timeseries_daily(business_id, d)
    # return list of {ds: 'YYYY-MM-DD', y: float} for JSON cache safety
    records: list[dict[str, object]] = []
    if ("ds" in ts.columns and "y" in ts.columns):
        records_df2: pd.DataFrame = cast(pd.DataFrame, ts[["ds", "y"]])
        to_dict_any2: Callable[..., object] = cast(Callable[..., object], getattr(records_df2, "to_dict"))
        records = cast(list[dict[str, object]], to_dict_any2(orient="records"))
    return [{"ds": _to_iso_date_str(rec.get("ds", "")), "y": _as_float(rec.get("y", 0.0))} for rec in records]
