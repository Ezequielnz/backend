from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.db.scoped_client import ScopedSupabaseClient
from app.schemas.branch_settings import BranchSettings, BranchSettingsUpdate


class BranchSettingsService:
    """
    Wrapper around `negocio_configuracion` that encapsulates default handling,
    validation and hydration into Pydantic models.
    """

    _SELECT_COLUMNS = (
        "negocio_id,"
        "inventario_modo,"
        "servicios_modo,"
        "catalogo_producto_modo,"
        "permite_transferencias,"
        "transferencia_auto_confirma,"
        "default_branch_id,"
        "metadata,"
        "created_at,"
        "updated_at"
    )

    def __init__(self, client: ScopedSupabaseClient, business_id: str) -> None:
        self._client = client
        self._business_id = business_id

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #
    def _select_query(self):
        return (
            self._client.table("negocio_configuracion")
            .select(self._SELECT_COLUMNS)
            .eq("negocio_id", self._business_id)
            .limit(1)
        )

    def _ensure_default_record(self) -> None:
        """
        Inserts a default configuration row if none exists for the negocio.
        Uses sensible defaults aligned with the structural migration.
        """
        defaults: Dict[str, Any] = {
            "negocio_id": self._business_id,
            "inventario_modo": "por_sucursal",
            "servicios_modo": "por_sucursal",
            "catalogo_producto_modo": "por_sucursal",
            "permite_transferencias": True,
            "transferencia_auto_confirma": False,
            "metadata": {},
        }
        try:
            self._client.table("negocio_configuracion").insert(defaults).execute()
        except Exception:
            # Ignore errors that indicate the record already exists or RLS rejected duplicates.
            pass

    def _hydrate(self, payload: Optional[Dict[str, Any]]) -> Optional[BranchSettings]:
        if not payload:
            return None

        metadata = payload.get("metadata")
        if metadata is None:
            payload["metadata"] = {}

        return BranchSettings(**payload)

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def fetch(self, ensure_exists: bool = True) -> Optional[BranchSettings]:
        response = self._select_query().execute()
        data = response.data[0] if response.data else None

        if data is None and ensure_exists:
            self._ensure_default_record()
            response = self._select_query().execute()
            data = response.data[0] if response.data else None

        return self._hydrate(data)

    def update(self, payload: BranchSettingsUpdate) -> BranchSettings:
        current = self.fetch(ensure_exists=True)
        if current is None:
            raise RuntimeError("Unable to retrieve branch settings before applying updates.")

        if not payload.has_updates():
            return current

        update_data: Dict[str, Any] = payload.model_dump(exclude_unset=True)

        metadata_payload = update_data.get("metadata")
        if metadata_payload is None:
            metadata_payload = dict(current.metadata or {})
        elif metadata_payload is None:
            metadata_payload = {}

        if "metadata" in update_data and update_data["metadata"] is None:
            metadata_payload = {}

        if (
            "inventario_modo" in update_data
            and update_data["inventario_modo"] != current.inventario_modo
        ):
            metadata_payload = dict(metadata_payload)
            metadata_payload["inventory_mode_previous"] = current.inventario_modo
            metadata_payload["inventory_mode_changed_at"] = datetime.now(timezone.utc).isoformat()
            metadata_payload["inventory_mode_sync_required"] = True

        update_data["metadata"] = metadata_payload

        # Normalize empty strings for default_branch_id to NULL so Supabase accepts it.
        default_branch = update_data.get("default_branch_id")
        if isinstance(default_branch, str) and not default_branch.strip():
            update_data["default_branch_id"] = None

        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        self._client.table("negocio_configuracion").update(update_data).eq(
            "negocio_id", self._business_id
        ).execute()

        updated = self.fetch(ensure_exists=True)
        if updated is None:
            raise RuntimeError("Branch settings update executed but record could not be reloaded.")

        return updated
