from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field

InventoryMode = str  # 'centralizado' | 'por_sucursal'
ServiceMode = str  # 'centralizado' | 'por_sucursal'
CatalogMode = str  # 'compartido' | 'por_sucursal'


class BranchSettings(BaseModel):
    """Pydantic schema that mirrors negocio_configuracion rows."""

    negocio_id: UUID
    inventario_modo: InventoryMode
    servicios_modo: ServiceMode
    catalogo_producto_modo: CatalogMode
    permite_transferencias: bool
    transferencia_auto_confirma: bool
    default_branch_id: Optional[UUID] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BranchSettingsUpdate(BaseModel):
    """Payload accepted when updating negocio_configuracion preferences."""

    inventario_modo: Optional[InventoryMode] = None
    servicios_modo: Optional[ServiceMode] = None
    catalogo_producto_modo: Optional[CatalogMode] = None
    permite_transferencias: Optional[bool] = None
    transferencia_auto_confirma: Optional[bool] = None
    default_branch_id: Optional[UUID] = None
    metadata: Optional[Dict[str, Any]] = None

    def has_updates(self) -> bool:
        return any(
            getattr(self, field) is not None
            for field in (
                "inventario_modo",
                "servicios_modo",
                "catalogo_producto_modo",
                "permite_transferencias",
                "transferencia_auto_confirma",
                "default_branch_id",
                "metadata",
            )
        )
