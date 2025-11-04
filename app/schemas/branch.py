from datetime import datetime
from typing import Optional
from uuid import UUID

from typing import Optional
from pydantic import BaseModel, Field


class Branch(BaseModel):
    """
    Lightweight schema for sucursales (branches) exposed via the API.
    Only includes fields required by the frontend selector.
    """

    id: UUID
    negocio_id: UUID
    nombre: str
    codigo: Optional[str] = None
    direccion: Optional[str] = None
    activo: bool = True
    is_main: bool = False
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None

    class Config:
        from_attributes = True


class BranchCreate(BaseModel):
    nombre: str = Field(..., min_length=1, description="Nombre legible de la sucursal")
    codigo: Optional[str] = Field(None, description="Código interno opcional")
    direccion: Optional[str] = Field(None, description="Dirección física de la sucursal")
    activo: bool = Field(default=True, description="Indica si la sucursal está operativa")
    is_main: bool = Field(default=False, description="Define si la sucursal es la principal del negocio")


class BranchUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1)
    codigo: Optional[str] = None
    direccion: Optional[str] = None
    activo: Optional[bool] = None
    is_main: Optional[bool] = None

    def has_updates(self) -> bool:
        return any(
            getattr(self, field) is not None
            for field in ("nombre", "codigo", "direccion", "activo", "is_main")
        )
