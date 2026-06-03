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
            from app.db.supabase_client import get_supabase_service_client
            svc_client = get_supabase_service_client()
            svc_client.table("negocio_configuracion").insert(defaults).execute()
        except Exception as e:
            # Ignore errors that indicate the record already exists or RLS rejected duplicates.
            print(f"Error inserting default config: {e}")
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
        is_new = current is None

        if not is_new and not payload.has_updates():
            return current

        update_data: Dict[str, Any] = payload.model_dump(mode='json', exclude_unset=True)

        metadata_payload = update_data.get("metadata")
        if metadata_payload is None:
            metadata_payload = dict(current.metadata if current and current.metadata else {})
        elif metadata_payload is None:
            metadata_payload = {}

        if "metadata" in update_data and update_data["metadata"] is None:
            metadata_payload = {}

        if (
            current is not None
            and "inventario_modo" in update_data
            and update_data["inventario_modo"] != current.inventario_modo
        ):
            metadata_payload = dict(metadata_payload)
            metadata_payload["inventory_mode_previous"] = current.inventario_modo
            metadata_payload["inventory_mode_changed_at"] = datetime.now(timezone.utc).isoformat()
            metadata_payload["inventory_mode_sync_required"] = False

        if (
            current is not None
            and "servicios_modo" in update_data
            and update_data["servicios_modo"] != current.servicios_modo
        ):
            metadata_payload = dict(metadata_payload)
            metadata_payload["services_mode_previous"] = current.servicios_modo
            metadata_payload["services_mode_changed_at"] = datetime.now(timezone.utc).isoformat()
            metadata_payload["services_mode_sync_required"] = False

        update_data["metadata"] = metadata_payload

        # Normalize empty strings for default_branch_id to NULL so Supabase accepts it.
        default_branch = update_data.get("default_branch_id")
        if isinstance(default_branch, str) and not default_branch.strip():
            update_data["default_branch_id"] = None

        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        from app.db.supabase_client import get_supabase_service_client
        
        if is_new:
            update_data["negocio_id"] = self._business_id
            update_data["created_at"] = update_data["updated_at"]
            if "inventario_modo" not in update_data:
                update_data["inventario_modo"] = "por_sucursal"
            if "servicios_modo" not in update_data:
                update_data["servicios_modo"] = "por_sucursal"
            if "catalogo_producto_modo" not in update_data:
                update_data["catalogo_producto_modo"] = "por_sucursal"
            if "permite_transferencias" not in update_data:
                update_data["permite_transferencias"] = True
            if "transferencia_auto_confirma" not in update_data:
                update_data["transferencia_auto_confirma"] = False
            
            try:
                svc_client = get_supabase_service_client()
                svc_client.table("negocio_configuracion").insert(update_data).execute()
            except Exception as e:
                # Fallback to scoped client
                self._client.table("negocio_configuracion").insert(update_data).execute()
        else:
            try:
                svc_client = get_supabase_service_client()
                svc_client.table("negocio_configuracion").update(update_data).eq(
                    "negocio_id", self._business_id
                ).execute()
            except Exception as e:
                # Fallback to scoped client
                self._client.table("negocio_configuracion").update(update_data).eq(
                    "negocio_id", self._business_id
                ).execute()

        updated = self.fetch(ensure_exists=False)
        if updated is None:
            raise RuntimeError("Branch settings update executed but record could not be reloaded.")

        # Run synchronization if modes changed
        if current is not None:
            try:
                from app.services.sync_service import SyncService
                sync_svc = SyncService(self._business_id)
                
                if "inventario_modo" in update_data and update_data["inventario_modo"] != current.inventario_modo:
                    sync_svc.sync_inventory_mode(current.inventario_modo, update_data["inventario_modo"])
                    
                if "servicios_modo" in update_data and update_data["servicios_modo"] != current.servicios_modo:
                    sync_svc.sync_services_mode(current.servicios_modo, update_data["servicios_modo"])
            except Exception as e:
                # Log error but don't fail the update entirely, API can return 500 or just log it
                # For robustness, we let it raise so the endpoint catches it and returns 500
                raise RuntimeError(f"Error synchronizing branch settings: {str(e)}") from e

        return updated
