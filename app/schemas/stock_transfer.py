from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

StockTransferStatus = Literal["borrador", "confirmada", "cancelada", "recibida"]


class StockTransferItemBase(BaseModel):
    """Common fields for stock transfer line items."""

    producto_id: UUID
    cantidad: Decimal = Field(gt=0, description="Cantidad a transferir (mayor a 0).")
    unidad: Optional[str] = None
    lote: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StockTransferItemCreate(StockTransferItemBase):
    """Payload schema for creating transfer line items."""


class StockTransferItem(StockTransferItemBase):
    """Persistent representation of a transfer line item."""

    id: UUID
    transferencia_id: UUID
    negocio_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class StockTransferCreate(BaseModel):
    """Schema used to create a new stock transfer."""

    origen_sucursal_id: UUID
    destino_sucursal_id: UUID
    comentarios: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    items: List[StockTransferItemCreate]

    @model_validator(mode="after")
    def _validate_payload(self) -> "StockTransferCreate":
        if self.origen_sucursal_id == self.destino_sucursal_id:
            raise ValueError("La sucursal de origen y destino deben ser distintas.")
        if not self.items:
            raise ValueError("Debe especificar al menos un producto a transferir.")
        return self


class StockTransfer(BaseModel):
    """Full representation of a stock transfer, including details."""

    id: UUID
    negocio_id: UUID
    origen_sucursal_id: UUID
    destino_sucursal_id: UUID
    estado: StockTransferStatus
    inventario_modo_source: Optional[str] = None
    inventario_modo_target: Optional[str] = None
    permite_transferencias_snapshot: Optional[bool] = None
    creado_por: UUID
    aprobado_por: Optional[UUID] = None
    comentarios: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    items: List[StockTransferItem] = Field(default_factory=list)

    class Config:
        from_attributes = True
