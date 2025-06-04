from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime

class ClienteBase(BaseModel):
    """Base schema for client data."""
    nombre: str = Field(..., min_length=1, max_length=100, description="Nombre del cliente")
    apellido: Optional[str] = Field(None, max_length=100, description="Apellido del cliente")
    documento_tipo: Optional[str] = Field(None, max_length=20, description="Tipo de documento (DNI, CUIT, etc.)")
    documento_numero: Optional[str] = Field(None, max_length=20, description="Número de documento")
    email: Optional[EmailStr] = Field(None, description="Email del cliente")
    telefono: Optional[str] = Field(None, max_length=20, description="Teléfono del cliente")
    direccion: Optional[str] = Field(None, max_length=200, description="Dirección del cliente")

class ClienteCreate(ClienteBase):
    """Schema for creating a new client."""
    pass

class ClienteUpdate(BaseModel):
    """Schema for updating a client."""
    nombre: Optional[str] = Field(None, min_length=1, max_length=100, description="Nombre del cliente")
    apellido: Optional[str] = Field(None, max_length=100, description="Apellido del cliente")
    documento_tipo: Optional[str] = Field(None, max_length=20, description="Tipo de documento (DNI, CUIT, etc.)")
    documento_numero: Optional[str] = Field(None, max_length=20, description="Número de documento")
    email: Optional[EmailStr] = Field(None, description="Email del cliente")
    telefono: Optional[str] = Field(None, max_length=20, description="Teléfono del cliente")
    direccion: Optional[str] = Field(None, max_length=200, description="Dirección del cliente")

class Cliente(ClienteBase):
    """Schema for client response."""
    id: str = Field(..., description="UUID del cliente")
    negocio_id: str = Field(..., description="UUID del negocio al que pertenece el cliente")
    creado_en: Optional[datetime] = Field(None, description="Fecha de creación")
    actualizado_en: Optional[datetime] = Field(None, description="Fecha de última actualización")

    class Config:
        from_attributes = True

class ClienteSearch(BaseModel):
    """Schema for client search parameters."""
    q: Optional[str] = Field(None, description="Búsqueda por nombre, apellido, email o documento")
    documento_tipo: Optional[str] = Field(None, description="Filtrar por tipo de documento")
    limit: Optional[int] = Field(10, ge=1, le=100, description="Límite de resultados")
    offset: Optional[int] = Field(0, ge=0, description="Offset para paginación") 