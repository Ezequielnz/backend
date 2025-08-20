from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field, EmailStr


class ProveedorBase(BaseModel):
    nombre: str = Field(..., description="Nombre del proveedor")
    cuit_cuil: Optional[str] = Field(None, description="CUIT/CUIL del proveedor")
    email: Optional[EmailStr] = Field(None, description="Email del proveedor")
    telefono: Optional[str] = Field(None, description="Teléfono del proveedor")
    direccion: Optional[str] = Field(None, description="Dirección del proveedor")
    ciudad: Optional[str] = Field(None, description="Ciudad del proveedor")
    provincia: Optional[str] = Field(None, description="Provincia del proveedor")
    pais: Optional[str] = Field(None, description="País del proveedor")
    condiciones_pago: Optional[str] = Field(None, description="Condiciones de pago")
    observaciones: Optional[str] = Field(None, description="Observaciones adicionales")
    estado: Optional[str] = Field(None, description="Estado del proveedor")


class ProveedorCreate(ProveedorBase):
    pass


class ProveedorUpdate(BaseModel):
    nombre: Optional[str] = None
    cuit_cuil: Optional[str] = None
    email: Optional[EmailStr] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    provincia: Optional[str] = None
    pais: Optional[str] = None
    condiciones_pago: Optional[str] = None
    observaciones: Optional[str] = None
    estado: Optional[str] = None


class Proveedor(ProveedorBase):
    id: str
    negocio_id: str
