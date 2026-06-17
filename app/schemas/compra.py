from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field, validator
from datetime import date


class CompraItem(BaseModel):
    producto_id: str = Field(..., description="ID del producto comprado")
    cantidad: float = Field(..., gt=0, description="Cantidad comprada")
    precio_unitario: float = Field(..., gt=0, description="Precio unitario de compra")

    @validator("producto_id")
    def validate_producto_id(cls, v: str) -> str:
        if not v or not isinstance(v, str):
            raise ValueError("producto_id inválido")
        return v


class CompraCreate(BaseModel):
    proveedor_id: Optional[str] = Field(None, description="ID del proveedor")
    proveedor_razon_social: Optional[str] = Field(None, description="Razón social del proveedor si no hay ID")
    fecha: Optional[date] = Field(None, description="Fecha de la compra")
    metodo_pago: Optional[str] = Field(None, description="Método de pago de la compra")
    estado: Optional[str] = Field(None, description="Estado de entrega de la compra ('entregado'|'no_entregado')")
    fecha_entrega: Optional[date] = Field(None, description="Fecha estimada/real de entrega")
    observaciones: Optional[str] = Field(None, max_length=500)
    items: List[CompraItem] = Field(...)

    @validator("proveedor_razon_social")
    def validate_proveedor_razon_social(cls, v, values):
        # Allow either proveedor_id or proveedor_razon_social or none (depending on DB constraints)
        return v

    @validator("items")
    def validate_items(cls, v: List[CompraItem]) -> List[CompraItem]:
        if not v or len(v) < 1:
            raise ValueError("La compra debe contener al menos un ítem")
        return v


class CompraUpdate(BaseModel):
    proveedor_id: Optional[str] = None
    proveedor_razon_social: Optional[str] = None
    fecha: Optional[date] = None
    fecha_entrega: Optional[date] = None
    estado: Optional[str] = None
    observaciones: Optional[str] = Field(None, max_length=500)
