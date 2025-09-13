from __future__ import annotations

import os
from typing import cast, ClassVar, Callable
from collections.abc import Mapping
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from app.db.supabase_client import get_supabase_service_client, TableQueryProto, APIResponseProto


class MLSettings(BaseSettings):
    # Candidates and selection
    ML_MODEL_CANDIDATES: str = Field(default=os.getenv("ML_MODEL_CANDIDATES", "prophet"))
    ML_SELECT_BEST: bool = Field(default=os.getenv("ML_SELECT_BEST", "false").lower() == "true")
    ML_CV_PRIMARY_METRIC: str = Field(default=os.getenv("ML_CV_PRIMARY_METRIC", "mape"))

    # Cross-validation and horizon
    ML_HORIZON_DAYS: int = Field(default=int(os.getenv("ML_HORIZON_DAYS", "14")))
    ML_CV_FOLDS: int = Field(default=int(os.getenv("ML_CV_FOLDS", "3")))

    # Prophet/SARIMAX and anomalies
    ML_SEASONALITY_MODE: str = Field(default=os.getenv("ML_SEASONALITY_MODE", "additive"))
    ML_HOLIDAYS_COUNTRY: str = Field(default=os.getenv("ML_HOLIDAYS_COUNTRY", ""))
    ML_LOG_TRANSFORM: bool = Field(default=os.getenv("ML_LOG_TRANSFORM", "false").lower() == "true")
    ML_SARIMAX_ORDER: str = Field(default=os.getenv("ML_SARIMAX_ORDER", "1,1,1"))
    ML_SARIMAX_SEASONAL: str = Field(default=os.getenv("ML_SARIMAX_SEASONAL", ""))
    ML_ANOMALY_METHOD: str = Field(default=os.getenv("ML_ANOMALY_METHOD", "iforest"))
    ML_STL_PERIOD: int = Field(default=int(os.getenv("ML_STL_PERIOD", "7")))
    ML_STL_ZTHRESH: float = Field(default=float(os.getenv("ML_STL_ZTHRESH", "3.0")))

    # Windows and re-train
    ML_MAX_TRAIN_WINDOW_DAYS: int = Field(default=int(os.getenv("ML_MAX_TRAIN_WINDOW_DAYS", "730")))
    ML_RETRAIN_CRON: str = Field(default=os.getenv("ML_RETRAIN_CRON", "@weekly"))

    # Multi-tenant control
    # "*" = all tenants; otherwise comma-separated list of tenant_ids
    ML_TENANT_IDS: str = Field(default=os.getenv("ML_TENANT_IDS", "*"))

    # Alerts
    ML_ERROR_ALERT_MAPE: float = Field(default=float(os.getenv("ML_ERROR_ALERT_MAPE", "0.25")))

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        # Ignore unrelated env vars (e.g., SUPABASE_URL) when loading settings
        extra="ignore",
    )

    def allowed_tenants(self) -> set[str]:
        raw = (self.ML_TENANT_IDS or "").strip()
        if raw == "*" or raw == "":
            return set()
        return {t.strip() for t in raw.split(",") if t.strip()}

    def get_tenant_overrides(self, tenant_id: str) -> dict[str, object]:
        """
        Optional per-tenant overrides via table `tenant_ml_settings` with columns:
        - tenant_id (text)
        - settings (jsonb)  -- keys matching the ML_* names above
        If the table doesn't exist or the row is absent, returns {}.
        """
        try:
            svc = get_supabase_service_client()
            table_fn: Callable[[str], object] = cast(Callable[[str], object], getattr(svc, "table"))
            tbl: TableQueryProto = cast(TableQueryProto, table_fn("tenant_ml_settings"))
            q: TableQueryProto = tbl.select("settings").eq("tenant_id", tenant_id).limit(1)
            res: APIResponseProto = q.execute()
            rows_obj: object = getattr(res, "data", []) or []
            rows: list[Mapping[str, object]] = cast(list[Mapping[str, object]], rows_obj) if isinstance(rows_obj, list) else []
            if rows:
                s_obj: object | None = rows[0].get("settings")
                if isinstance(s_obj, Mapping):
                    s_map: Mapping[object, object] = cast(Mapping[object, object], s_obj)
                    return {str(k): v for k, v in s_map.items()}
        except Exception:
            # Table may not exist yet; ignore silently
            pass
        return {}


ml_settings = MLSettings()  # singleton
