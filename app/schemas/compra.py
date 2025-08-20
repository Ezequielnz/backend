from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field, validator
from datetime import date


class CompraItem(BaseModel):
    producto_id: str = Field(..., description="ID del producto comprado")
    cantidad: int = Field(..., gt=0, description="Cantidad comprada")
    precio_unitario: float = Field(..., gt=0, description="Precio unitario de compra")

    @validator("producto_id")
    def validate_producto_id(cls, v: str) -> str:
        if not v or not isinstance(v, str):
            raise ValueError("producto_id inválido")
        return v


class CompraCreate(BaseModel):
    proveedor_id: Optional[str] = Field(None, description="ID del proveedor")
    proveedor_nombre: Optional[str] = Field(None, description="Nombre del proveedor si no hay ID")
    fecha: Optional[date] = Field(None, description="Fecha de la compra")
    observaciones: Optional[str] = Field(None, max_length=500)
    items: List[CompraItem] = Field(..., min_items=1)

    @validator("proveedor_nombre")
    def validate_proveedor_nombre(cls, v, values):
        # Allow either proveedor_id or proveedor_nombre or none (depending on DB constraints)
        return v


class CompraUpdate(BaseModel):
    proveedor_id: Optional[str] = None
    proveedor_nombre: Optional[str] = None
    fecha: Optional[date] = None
    observaciones: Optional[str] = Field(None, max_length=500)
