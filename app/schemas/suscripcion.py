from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum

class TipoSuscripcion(str, Enum):
    MENSUAL = "mensual"
    TRIMESTRAL = "trimestral"
    SEMESTRAL = "semestral"
    ANUAL = "anual"

class EstadoSuscripcion(str, Enum):
    ACTIVA = "activa"
    PAUSADA = "pausada"
    CANCELADA = "cancelada"
    VENCIDA = "vencida"

class SuscripcionBase(BaseModel):
    """Base schema for subscription data."""
    nombre: str = Field(..., min_length=1, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=1000)
    precio_mensual: float = Field(..., gt=0)
    tipo: TipoSuscripcion = Field(default=TipoSuscripcion.MENSUAL)
    estado: EstadoSuscripcion = Field(default=EstadoSuscripcion.ACTIVA)
    fecha_inicio: datetime
    fecha_fin: Optional[datetime] = None
    fecha_proximo_pago: Optional[datetime] = None

class SuscripcionCreate(BaseModel):
    """Schema for creating a new subscription."""
    cliente_id: str = Field(..., description="UUID del cliente")
    servicio_id: str = Field(..., description="UUID del servicio")
    nombre: str = Field(..., min_length=1, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=1000)
    precio_mensual: float = Field(..., gt=0)
    tipo: TipoSuscripcion = Field(default=TipoSuscripcion.MENSUAL)
    fecha_inicio: datetime
    fecha_fin: Optional[datetime] = None
    fecha_proximo_pago: Optional[datetime] = None

class SuscripcionUpdate(BaseModel):
    """Schema for updating a subscription."""
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=1000)
    precio_mensual: Optional[float] = Field(None, gt=0)
    tipo: Optional[TipoSuscripcion] = None
    estado: Optional[EstadoSuscripcion] = None
    fecha_fin: Optional[datetime] = None
    fecha_proximo_pago: Optional[datetime] = None
    activa: Optional[bool] = None

class Suscripcion(SuscripcionBase):
    """Schema for subscription response."""
    id: str
    negocio_id: str = Field(..., description="UUID del negocio")
    cliente_id: str = Field(..., description="UUID del cliente")
    servicio_id: str = Field(..., description="UUID del servicio")
    activa: bool = Field(default=True, description="Indica si la suscripción está activa")
    creado_en: datetime
    actualizado_en: datetime

    class Config:
        from_attributes = True 