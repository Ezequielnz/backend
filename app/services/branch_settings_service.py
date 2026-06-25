from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.db.scoped_client import ScopedSupabaseClient
from app.db.supabase_client import get_supabase_service_client
from app.schemas.branch_settings import BranchSettings, BranchSettingsUpdate
from app.services.config_cache import invalidate_negocio_config

logger = logging.getLogger(__name__)


class BranchSettingsService:
    """
    Wrapper around `negocio_configuracion` that encapsulates default handling,
    validation and hydration into Pydantic models.

    Writes always use the service-role client (bypasses RLS) so updates are
    never silently dropped due to missing RLS UPDATE/INSERT policies.
    Reads use the user-scoped client so RLS still gates visibility.
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
        # Service client always bypasses RLS — used for all writes.
        self._svc = get_supabase_service_client()

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #
    def _select_query(self):
        """Use service client for reads too, to avoid RLS SELECT issues."""
        return (
            self._svc.table("negocio_configuracion")
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
            "inventario_modo": "centralizado",
            "servicios_modo": "centralizado",
            "catalogo_producto_modo": "compartido",
            "permite_transferencias": True,
            "transferencia_auto_confirma": False,
            "metadata": {},
        }
        try:
            self._svc.table("negocio_configuracion").insert(defaults).execute()
            logger.info("Created default negocio_configuracion for %s", self._business_id)
        except Exception as e:
            # Silently ignore duplicate key errors — record already exists.
            logger.debug("Default config insert skipped (likely already exists): %s", e)

    def _hydrate(self, payload: Optional[Dict[str, Any]]) -> Optional[BranchSettings]:
        if not payload:
            return None

        if payload.get("metadata") is None:
            payload["metadata"] = {}

        return BranchSettings(**payload)

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def fetch(self, ensure_exists: bool = True) -> Optional[BranchSettings]:
        try:
            response = self._select_query().execute()
            data = response.data[0] if response.data else None

            if data is None and ensure_exists:
                self._ensure_default_record()
                response = self._select_query().execute()
                data = response.data[0] if response.data else None

            return self._hydrate(data)
        except Exception as e:
            logger.error(f"Error fetching branch settings for {self._business_id}: {e}")
            return None

    def update(self, payload: BranchSettingsUpdate) -> BranchSettings:
        current = self.fetch(ensure_exists=True)
        is_new = current is None

        if not is_new and not payload.has_updates():
            return current  # type: ignore[return-value]

        update_data: Dict[str, Any] = payload.model_dump(mode="json", exclude_unset=True)

        # ------------------------------------------------------------------ #
        # Metadata bookkeeping
        # ------------------------------------------------------------------ #
        metadata_payload: Dict[str, Any] = dict(
            current.metadata if current and current.metadata else {}
        )
        # Explicit metadata in payload overrides
        if "metadata" in update_data and update_data["metadata"] is not None:
            metadata_payload = update_data["metadata"]

        if (
            current is not None
            and "inventario_modo" in update_data
            and update_data["inventario_modo"] != current.inventario_modo
        ):
            metadata_payload["inventory_mode_previous"] = current.inventario_modo
            metadata_payload["inventory_mode_changed_at"] = datetime.now(timezone.utc).isoformat()

        if (
            current is not None
            and "servicios_modo" in update_data
            and update_data["servicios_modo"] != current.servicios_modo
        ):
            metadata_payload["services_mode_previous"] = current.servicios_modo
            metadata_payload["services_mode_changed_at"] = datetime.now(timezone.utc).isoformat()

        if (
            current is not None
            and "catalogo_producto_modo" in update_data
            and update_data["catalogo_producto_modo"] != current.catalogo_producto_modo
        ):
            metadata_payload["product_catalog_mode_previous"] = current.catalogo_producto_modo
            metadata_payload["product_catalog_mode_changed_at"] = datetime.now(timezone.utc).isoformat()

        update_data["metadata"] = metadata_payload

        # Normalize empty string → NULL for UUID column.
        default_branch = update_data.get("default_branch_id")
        if isinstance(default_branch, str) and not default_branch.strip():
            update_data["default_branch_id"] = None

        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        # ------------------------------------------------------------------ #
        # Persist — always via service client (bypasses RLS)
        # ------------------------------------------------------------------ #
        if is_new:
            update_data["negocio_id"] = self._business_id
            update_data.setdefault("inventario_modo", "centralizado")
            update_data.setdefault("servicios_modo", "centralizado")
            update_data.setdefault("catalogo_producto_modo", "compartido")
            update_data.setdefault("permite_transferencias", True)
            update_data.setdefault("transferencia_auto_confirma", False)
            update_data.setdefault("created_at", update_data["updated_at"])

            resp = self._svc.table("negocio_configuracion").insert(update_data).execute()
            if not resp.data:
                raise RuntimeError(
                    f"Failed to insert negocio_configuracion for {self._business_id}. "
                    f"Response: {resp}"
                )
            logger.info("Inserted new negocio_configuracion for %s", self._business_id)
        else:
            resp = (
                self._svc.table("negocio_configuracion")
                .update(update_data)
                .eq("negocio_id", self._business_id)
                .execute()
            )
            if not resp.data:
                raise RuntimeError(
                    f"Failed to update negocio_configuracion for {self._business_id}. "
                    f"Zero rows affected. Response: {resp}"
                )
            logger.info(
                "Updated negocio_configuracion for %s — fields: %s",
                self._business_id,
                list(update_data.keys()),
            )

        # ------------------------------------------------------------------ #
        # Reload to return the definitive persisted state
        # ------------------------------------------------------------------ #
        updated = self.fetch(ensure_exists=False)
        if updated is None:
            raise RuntimeError(
                f"Branch settings update executed for {self._business_id} "
                "but record could not be reloaded."
            )

        # ------------------------------------------------------------------ #
        # Background data synchronisation (inventory / services mode changes)
        # NOTE: This runs AFTER returning the updated config, but if sync fails,
        # we manually roll back the configuration to prevent an inconsistent state.
        # ------------------------------------------------------------------ #
        if current is not None:
            inv_changed = (
                "inventario_modo" in update_data
                and update_data["inventario_modo"] != current.inventario_modo
            )
            svc_changed = (
                "servicios_modo" in update_data
                and update_data["servicios_modo"] != current.servicios_modo
            )
            cat_changed = (
                "catalogo_producto_modo" in update_data
                and update_data["catalogo_producto_modo"] != current.catalogo_producto_modo
            )
            
            if inv_changed or svc_changed or cat_changed:
                try:
                    from app.services.sync_service import SyncService
                    sync_svc = SyncService(self._business_id)
                    if inv_changed:
                        sync_svc.sync_inventory_mode(
                            current.inventario_modo, update_data["inventario_modo"]
                        )
                    if svc_changed:
                        sync_svc.sync_services_mode(
                            current.servicios_modo, update_data["servicios_modo"]
                        )
                    if cat_changed:
                        sync_svc.sync_product_catalog_mode(
                            current.catalogo_producto_modo, update_data["catalogo_producto_modo"]
                        )
                except Exception as e:
                    logger.error(
                        "Sync error for %s. Rolling back configuration to prevent inconsistent state: %s",
                        self._business_id,
                        e,
                    )
                    # Rollback the configuration to its previous state
                    rollback_data = {}
                    if inv_changed:
                        rollback_data["inventario_modo"] = current.inventario_modo
                    if svc_changed:
                        rollback_data["servicios_modo"] = current.servicios_modo
                    if cat_changed:
                        rollback_data["catalogo_producto_modo"] = current.catalogo_producto_modo
                    
                    try:
                        self._svc.table("negocio_configuracion").update(rollback_data).eq("negocio_id", self._business_id).execute()
                    except Exception as rollback_err:
                        logger.critical("CRITICAL: Failed to rollback branch settings for %s: %s", self._business_id, rollback_err)
                        
                    raise RuntimeError("Sincronización fallida. Se han revertido los cambios para mantener la consistencia.") from e
        # Invalidate the cache for this business
        invalidate_negocio_config(self._business_id)

        return updated
