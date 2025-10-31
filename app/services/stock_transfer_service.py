from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID, uuid4

from app.db.scoped_client import ScopedSupabaseClient
from app.schemas.branch_settings import BranchSettings
from app.schemas.stock_transfer import (
    StockTransfer,
    StockTransferCreate,
    StockTransferItem,
    StockTransferItemCreate,
)

try:  # pragma: no cover - Celery not available during some tests
    from app.workers.action_worker import notify_stock_transfer_event
except Exception:  # pragma: no cover
    notify_stock_transfer_event = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

VALID_TRANSFER_STATES = {"borrador", "confirmada", "cancelada", "recibida"}


# --------------------------------------------------------------------------- #
# Custom exceptions
# --------------------------------------------------------------------------- #
class StockTransferError(RuntimeError):
    """Base error for stock transfer operations."""


class StockTransferNotAllowedError(StockTransferError):
    """Raised when transfers are disabled for the business."""


class StockTransferValidationError(StockTransferError):
    """Raised when input validation fails."""


class StockTransferNotFoundError(StockTransferError):
    """Raised when the transfer cannot be located."""


class StockTransferStateError(StockTransferError):
    """Raised on invalid state transitions."""


# --------------------------------------------------------------------------- #
# Service implementation
# --------------------------------------------------------------------------- #
class StockTransferService:
    """
    Encapsulates read/write operations for stock transfer headers + details.
    Applies business-level validation, inventory adjustments and event publishing.
    """

    def __init__(
        self,
        client: ScopedSupabaseClient,
        business_id: str,
        user_id: str,
        branch_settings: Optional[BranchSettings | Dict[str, Any]] = None,
    ) -> None:
        self._client = client
        self._business_id = str(business_id)
        self._user_id = user_id
        if isinstance(branch_settings, BranchSettings):
            self._settings: Optional[BranchSettings] = branch_settings
        elif isinstance(branch_settings, dict):
            self._settings = BranchSettings(**branch_settings)
        else:
            self._settings = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def list_transfers(
        self,
        *,
        estado: Optional[str] = None,
        origen_sucursal_id: Optional[str] = None,
        destino_sucursal_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[StockTransfer]:
        """
        Retrieve stock transfers for the current business, including their line items.
        """
        if estado and estado not in VALID_TRANSFER_STATES:
            raise StockTransferValidationError("Estado de transferencia no valido.")

        if limit is not None and limit <= 0:
            return []

        query = self._client.table("stock_transferencias").select("*").order(
            "created_at", desc=True
        )

        if estado:
            query = query.eq("estado", estado)
        if origen_sucursal_id:
            query = query.eq("origen_sucursal_id", origen_sucursal_id)
        if destino_sucursal_id:
            query = query.eq("destino_sucursal_id", destino_sucursal_id)
        if limit:
            query = query.limit(limit)

        response = query.execute()
        headers = response.data or []

        if not headers:
            return []

        transfer_ids = [str(row["id"]) for row in headers if row.get("id")]
        details_map: Dict[str, List[Dict[str, Any]]] = {transfer_id: [] for transfer_id in transfer_ids}

        if transfer_ids:
            details_resp = (
                self._client.table("stock_transferencias_detalle")
                .select("*")
                .in_("transferencia_id", transfer_ids)
                .execute()
            )
            for detail in details_resp.data or []:
                transfer_id = detail.get("transferencia_id")
                if not transfer_id:
                    continue
                if detail.get("metadata") is None:
                    detail["metadata"] = {}
                self._ensure_timestamp_defaults(detail, ("created_at", "updated_at"))
                details_map.setdefault(str(transfer_id), []).append(detail)

        transfers: List[StockTransfer] = []
        for header in headers:
            transfer_id = header.get("id")
            if not transfer_id:
                continue
            if header.get("metadata") is None:
                header["metadata"] = {}
            self._ensure_timestamp_defaults(header, ("created_at", "updated_at"))
            header["items"] = details_map.get(str(transfer_id), [])
            try:
                transfers.append(StockTransfer.model_validate(header))
            except Exception:
                logger.exception("No se pudo hidratar la transferencia %s", transfer_id)
                continue

        return transfers

    def create_transfer(self, payload: StockTransferCreate) -> StockTransfer:
        """Create a new stock transfer with its line items."""
        self._ensure_transfers_allowed()
        origin_id = str(payload.origen_sucursal_id)
        dest_id = str(payload.destino_sucursal_id)
        self._ensure_branch_exists(origin_id)
        self._ensure_branch_exists(dest_id)
        products = self._aggregate_quantities(payload.items)
        self._ensure_products_exist(products.keys())

        # Persist header first
        transfer_id = str(uuid4())
        header_data = {
            "id": transfer_id,
            "negocio_id": self._business_id,
            "origen_sucursal_id": origin_id,
            "destino_sucursal_id": dest_id,
            "estado": "borrador",
            "inventario_modo_source": self._settings.inventario_modo if self._settings else None,
            "inventario_modo_target": self._settings.inventario_modo if self._settings else None,
            "permite_transferencias_snapshot": self._settings.permite_transferencias if self._settings else True,
            "creado_por": self._user_id,
            "aprobado_por": None,
            "comentarios": payload.comentarios,
            "metadata": payload.metadata or {},
        }

        try:
            header_resp = self._client.table("stock_transferencias").insert(header_data).execute()
        except Exception as exc:  # pragma: no cover - Supabase client raises runtime errors
            raise StockTransferError(f"No se pudo crear la transferencia: {exc}") from exc

        if not header_resp.data:
            raise StockTransferError("No se pudo crear la transferencia de stock.")

        detail_rows = [
            {
                "transferencia_id": transfer_id,
                "negocio_id": self._business_id,
                "producto_id": str(item.producto_id),
                "cantidad": self._to_numeric(self._to_decimal(item.cantidad)),
                "unidad": item.unidad,
                "lote": item.lote,
                "metadata": item.metadata or {},
            }
            for item in payload.items
        ]

        try:
            detail_resp = (
                self._client.table("stock_transferencias_detalle").insert(detail_rows).execute()
            )
        except Exception as exc:  # pragma: no cover
            # Best-effort rollback of header if the details fail.
            self._client.table("stock_transferencias").delete().eq("id", transfer_id).execute()
            raise StockTransferError(f"No se pudieron registrar los productos: {exc}") from exc

        if not detail_resp.data:
            self._client.table("stock_transferencias").delete().eq("id", transfer_id).execute()
            raise StockTransferError("No se pudieron registrar los productos de la transferencia.")

        transfer = self.get_transfer(transfer_id)
        self._publish_event("created", transfer)

        if self._settings and self._settings.transferencia_auto_confirma:
            transfer = self.confirm_transfer(transfer.id, auto_trigger=True)

        return transfer

    def get_transfer(self, transfer_id: UUID | str) -> StockTransfer:
        """Fetch a transfer with its items."""
        transfer_uuid = str(transfer_id)
        header = self._fetch_single("stock_transferencias", id=transfer_uuid)
        if not header:
            raise StockTransferNotFoundError(f"Transferencia {transfer_uuid} no encontrada.")

        if header.get("metadata") is None:
            header["metadata"] = {}
        self._ensure_timestamp_defaults(header, ("created_at", "updated_at"))

        details_resp = (
            self._client.table("stock_transferencias_detalle")
            .select("*")
            .eq("transferencia_id", transfer_uuid)
            .execute()
        )
        detail_rows = details_resp.data or []
        for row in detail_rows:
            if row.get("metadata") is None:
                # Guarantee metadata dict for Pydantic conversion
                row["metadata"] = {}
            self._ensure_timestamp_defaults(row, ("created_at", "updated_at"))

        header["items"] = detail_rows
        return StockTransfer.model_validate(header)

    def confirm_transfer(self, transfer_id: UUID | str, *, auto_trigger: bool = False) -> StockTransfer:
        """Confirm a transfer, deducting inventory from the origin branch."""
        self._ensure_transfers_allowed()
        transfer = self.get_transfer(transfer_id)
        if transfer.estado != "borrador":
            raise StockTransferStateError("Solo las transferencias en borrador pueden confirmarse.")

        aggregated = self._aggregate_quantities(transfer.items)
        origin_id = str(transfer.origen_sucursal_id)
        self._ensure_stock_availability(origin_id, aggregated)

        if self._mode_per_branch():
            self._apply_inventory_adjustments(origin_id, aggregated, factor=Decimal("-1"))

        update_payload = {
            "estado": "confirmada",
            "aprobado_por": transfer.aprobado_por or self._user_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._client.table("stock_transferencias").update(update_payload).eq(
            "id", str(transfer.id)
        ).execute()

        updated = self.get_transfer(transfer.id)
        self._publish_event("confirmed", updated, {"auto_trigger": auto_trigger})
        return updated

    def receive_transfer(self, transfer_id: UUID | str) -> StockTransfer:
        """Mark a confirmed transfer as received, adding stock to the destination branch."""
        transfer = self.get_transfer(transfer_id)
        if transfer.estado != "confirmada":
            raise StockTransferStateError("Solo las transferencias confirmadas pueden marcarse como recibidas.")

        aggregated = self._aggregate_quantities(transfer.items)
        dest_id = str(transfer.destino_sucursal_id)

        if self._mode_per_branch():
            self._apply_inventory_adjustments(dest_id, aggregated, factor=Decimal("1"))

        update_payload = {
            "estado": "recibida",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._client.table("stock_transferencias").update(update_payload).eq(
            "id", str(transfer.id)
        ).execute()

        updated = self.get_transfer(transfer.id)
        self._publish_event("received", updated)
        return updated

    def delete_transfer(self, transfer_id: UUID | str) -> None:
        """Delete a draft transfer."""
        transfer = self.get_transfer(transfer_id)
        if transfer.estado != "borrador":
            raise StockTransferStateError("Solo las transferencias en borrador pueden eliminarse.")

        self._client.table("stock_transferencias").delete().eq("id", str(transfer.id)).execute()
        self._publish_event("deleted", transfer)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _ensure_transfers_allowed(self) -> None:
        if self._settings is not None and not self._settings.permite_transferencias:
            raise StockTransferNotAllowedError("Las transferencias de stock estan deshabilitadas para este negocio.")

    def _mode_per_branch(self) -> bool:
        """True when inventory is tracked separately per branch."""
        if self._settings is None:
            return True
        return self._settings.inventario_modo != "centralizado"

    def _ensure_branch_exists(self, branch_id: str) -> None:
        record = self._fetch_single("sucursales", id=branch_id)
        if not record:
            raise StockTransferValidationError(f"Sucursal {branch_id} no encontrada o sin acceso.")

    def _ensure_products_exist(self, product_ids: Iterable[str]) -> None:
        for product_id in product_ids:
            record = self._fetch_single("productos", id=product_id)
            if not record:
                raise StockTransferValidationError(
                    f"Producto {product_id} no pertenece al negocio o no existe."
                )

    def _fetch_single(self, table: str, **filters: Any) -> Optional[Dict[str, Any]]:
        query = self._client.table(table).select("*")
        for column, value in filters.items():
            query = query.eq(column, value)
        response = query.limit(1).execute()
        data = response.data or []
        return data[0] if data else None

    def _aggregate_quantities(
        self, items: Iterable[StockTransferItem | StockTransferItemCreate]
    ) -> Dict[str, Decimal]:
        totals: Dict[str, Decimal] = {}
        for item in items:
            producto_id = str(item.producto_id)
            cantidad = self._to_decimal(getattr(item, "cantidad"))
            totals[producto_id] = totals.get(producto_id, Decimal("0")) + cantidad
        return totals

    def _ensure_stock_availability(self, branch_id: str, aggregated: Dict[str, Decimal]) -> None:
        if not aggregated:
            raise StockTransferValidationError("La transferencia no contiene productos validos.")

        if self._mode_per_branch():
            for product_id, required in aggregated.items():
                available = self._get_branch_stock(branch_id, product_id)
                if available < required:
                    raise StockTransferValidationError(
                        f"Stock insuficiente en la sucursal origen para el producto {product_id}."
                    )
        else:
            for product_id, required in aggregated.items():
                available = self._get_business_stock(product_id)
                if available < required:
                    raise StockTransferValidationError(
                        f"Stock insuficiente en el inventario centralizado para el producto {product_id}."
                    )

    def _get_branch_stock(self, branch_id: str, product_id: str) -> Decimal:
        record = self._fetch_single(
            "inventario_sucursal", sucursal_id=branch_id, producto_id=product_id
        )
        if not record:
            return Decimal("0")
        return self._to_decimal(record.get("stock_actual"))

    def _get_business_stock(self, product_id: str) -> Decimal:
        record = self._fetch_single("inventario_negocio", producto_id=product_id)
        if not record:
            return Decimal("0")
        return self._to_decimal(record.get("stock_total"))

    def _apply_inventory_adjustments(
        self,
        branch_id: str,
        aggregated: Dict[str, Decimal],
        *,
        factor: Decimal,
    ) -> None:
        for product_id, quantity in aggregated.items():
            delta = quantity * factor
            record = self._fetch_single(
                "inventario_sucursal", sucursal_id=branch_id, producto_id=product_id
            )
            current_stock = self._to_decimal(record.get("stock_actual")) if record else Decimal("0")
            new_stock = current_stock + delta
            if new_stock < Decimal("0"):
                raise StockTransferValidationError(
                    f"La sucursal {branch_id} no tiene stock suficiente del producto {product_id}."
                )

            if record:
                self._client.table("inventario_sucursal").update(
                    {"stock_actual": self._to_numeric(new_stock)}
                ).eq("id", record["id"]).execute()
            else:
                insert_payload = {
                    "negocio_id": self._business_id,
                    "sucursal_id": branch_id,
                    "producto_id": product_id,
                    "stock_actual": self._to_numeric(new_stock),
                }
                self._client.table("inventario_sucursal").insert(insert_payload).execute()

    def _publish_event(
        self,
        event_type: str,
        transfer: StockTransfer,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        if notify_stock_transfer_event is None:  # pragma: no cover
            return
        payload = transfer.model_dump(mode="json")
        if extra:
            payload["event_metadata"] = extra
        try:
            notify_stock_transfer_event.delay(event_type, payload)  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover
            logger.warning("No se pudo publicar evento de transferencia: %s", exc)

    @staticmethod
    def _to_decimal(value: Any) -> Decimal:
        if isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        if value is None:
            return Decimal("0")
        return Decimal(str(value))

    @staticmethod
    def _to_numeric(value: Decimal) -> str:
        return format(value, "f")

    def _ensure_timestamp_defaults(self, payload: Dict[str, Any], fields: Iterable[str]) -> None:
        now = datetime.now(timezone.utc)
        for field in fields:
            if payload.get(field) is None:
                payload[field] = now
