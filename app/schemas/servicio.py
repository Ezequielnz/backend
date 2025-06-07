from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class ServicioBase(BaseModel):
    """Base schema for service data."""
    nombre: str = Field(..., min_length=1, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=1000)
    precio: float = Field(..., gt=0)
    duracion_minutos: Optional[int] = Field(None, ge=0)
    categoria_id: Optional[str] = Field(None, description="UUID de la categoría")
    tipo: Optional[str] = Field(default="mensual", description="Tipo de servicio")

class ServicioCreate(BaseModel):
    """Schema for creating a new service."""
    nombre: str = Field(..., min_length=1, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=1000)
    precio: float = Field(..., gt=0)
    duracion_minutos: Optional[int] = Field(None, ge=0)
    categoria_id: Optional[str] = Field(None, description="UUID de la categoría")
    tipo: Optional[str] = Field(default="mensual", description="Tipo de servicio")

class ServicioUpdate(BaseModel):
    """Schema for updating a service."""
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=1000)
    precio: Optional[float] = Field(None, gt=0)
    duracion_minutos: Optional[int] = Field(None, ge=0)
    categoria_id: Optional[str] = Field(None, description="UUID de la categoría")
    tipo: Optional[str] = Field(None, description="Tipo de servicio")
    activo: Optional[bool] = None

class Servicio(ServicioBase):
    """Schema for service response."""
    id: str
    negocio_id: str = Field(..., description="UUID del negocio")
    activo: bool = Field(default=True, description="Indica si el servicio está activo")
    tipo: Optional[str] = Field(default="mensual", description="Tipo de servicio")
    creado_en: datetime
    actualizado_en: datetime

    class Config:
        from_attributes = True 