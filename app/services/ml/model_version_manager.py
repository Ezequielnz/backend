from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast, Callable
from collections.abc import Mapping
from supabase.client import Client
import base64

from decimal import Decimal
import joblib

from app.db.supabase_client import get_supabase_service_client, APIResponseProto

logger = logging.getLogger(__name__)


@dataclass
class SavedModel:
    id: str
    tenant_id: str
    model_type: str
    model_version: str
    accuracy: float | None
    created_at: str


class ModelVersionManager:
    """
    Saves and loads ML models to/from Supabase `ml_models` table.
    Uses BYTEA column `model_data` to store joblib-serialized bytes.
    """

    def __init__(self) -> None:
        super().__init__()
        self.client: Client = get_supabase_service_client()

    def _serialize(self, model: object) -> bytes:
        buf = io.BytesIO()
        dump_any: Callable[..., object] = cast(Callable[..., object], getattr(joblib, "dump"))
        _ignored: object = dump_any(model, buf)
        return buf.getvalue()

    def _deserialize(self, data: bytes) -> object:
        buf = io.BytesIO(data)
        load_any: Callable[..., object] = cast(Callable[..., object], getattr(joblib, "load"))
        return load_any(buf)

    def save_model(
        self,
        tenant_id: str,
        model_type: str,
        model: object,
        model_version: str = "1.0",
        hyperparameters: Mapping[str, object] | None = None,
        training_metrics: Mapping[str, object] | None = None,
        accuracy: float | None = None,
        is_active: bool = True,
    ) -> SavedModel:
        data_bytes = self._serialize(model)
        row: dict[str, object] = {
            "tenant_id": tenant_id,
            "model_type": model_type,
            "model_version": model_version,
            # PostgREST expects JSON; encode bytea as base64 string
            "model_data": base64.b64encode(data_bytes).decode("ascii"),
            "hyperparameters": dict(hyperparameters) if hyperparameters is not None else {},
            "training_metrics": dict(training_metrics) if training_metrics is not None else {},
            "accuracy": accuracy,
            "is_active": is_active,
            "last_trained": datetime.now(timezone.utc).isoformat(),
        }
        # upsert per (tenant_id, model_type, model_version)
        table_fn: Callable[..., object] = cast(Callable[..., object], getattr(self.client, "table"))
        tbl = table_fn("ml_models")
        upsert_fn: Callable[..., object] = cast(Callable[..., object], getattr(tbl, "upsert"))
        query = upsert_fn(row, on_conflict="tenant_id,model_type,model_version")
        execute_fn: Callable[..., object] = cast(Callable[..., object], getattr(query, "execute"))
        _resp_obj = execute_fn()
        res = cast(APIResponseProto, _resp_obj)
        data_row: dict[str, object] = (res.data or [])[0]
        # Safely coerce accuracy to float | None for typing/runtime compatibility
        acc_obj = data_row.get("accuracy")
        if isinstance(acc_obj, (int, float)):
            acc_val: float | None = float(acc_obj)
        elif isinstance(acc_obj, str):
            try:
                acc_val = float(acc_obj)
            except ValueError:
                acc_val = None
        elif isinstance(acc_obj, Decimal):
            acc_val = float(acc_obj)
        else:
            acc_val = None
        return SavedModel(
            id=cast(str, data_row["id"]),
            tenant_id=cast(str, data_row["tenant_id"]),
            model_type=cast(str, data_row["model_type"]),
            model_version=cast(str, data_row["model_version"]),
            accuracy=acc_val,
            created_at=cast(str, data_row.get("created_at", datetime.now(timezone.utc).isoformat())),
        )

    def load_active_model(self, tenant_id: str, model_type: str) -> object | None:
        table_fn: Callable[..., object] = cast(Callable[..., object], getattr(self.client, "table"))
        tbl = table_fn("ml_models")
        select_fn: Callable[..., object] = cast(Callable[..., object], getattr(tbl, "select"))
        query = select_fn("id, model_data, is_active")
        eq_fn: Callable[..., object] = cast(Callable[..., object], getattr(query, "eq"))
        query = eq_fn("tenant_id", tenant_id)
        eq_fn2: Callable[..., object] = cast(Callable[..., object], getattr(query, "eq"))
        query = eq_fn2("model_type", model_type)
        eq_fn3: Callable[..., object] = cast(Callable[..., object], getattr(query, "eq"))
        query = eq_fn3("is_active", True)
        order_fn: Callable[..., object] = cast(Callable[..., object], getattr(query, "order"))
        query = order_fn("last_trained", desc=True)
        limit_fn: Callable[..., object] = cast(Callable[..., object], getattr(query, "limit"))
        query = limit_fn(1)
        execute_fn: Callable[..., object] = cast(Callable[..., object], getattr(query, "execute"))
        _resp_obj = execute_fn()
        res = cast(APIResponseProto, _resp_obj)
        rows_list: list[dict[str, object]] = res.data or []
        if not rows_list:
            return None
        blob = rows_list[0].get("model_data")
        if isinstance(blob, str):
            # supabase-py may return base64 for bytea; handle both bytes and b64
            try:
                data = base64.b64decode(blob)
            except Exception:
                logger.warning("Model data is string but not base64; cannot deserialize")
                return None
        else:
            data = blob  # type: ignore[assignment]
        if not isinstance(data, (bytes, bytearray)):
            logger.warning("Model data is not bytes; cannot deserialize")
            return None
        return self._deserialize(bytes(data))
