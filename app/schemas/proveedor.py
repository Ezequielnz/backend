from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field, EmailStr


class ProveedorBase(BaseModel):
    razon_social: str = Field(..., description="Razón social o nombre del proveedor")
    documento_tipo: Optional[str] = Field("CUIT", description="Tipo de documento (CUIT, DNI, etc.)")
    documento_numero: Optional[str] = Field(None, description="Número de documento (CUIT/CUIL/DNI)")
    condicion_iva: Optional[str] = Field(None, description="Condición frente al IVA")
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
    razon_social: Optional[str] = None
    documento_tipo: Optional[str] = None
    documento_numero: Optional[str] = None
    condicion_iva: Optional[str] = None
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
