from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime
from enum import Enum

class TipoSuscripcion(str, Enum):
    SEMANAL = "semanal"
    MENSUAL = "mensual"
    TRIMESTRAL = "trimestral"
    CUATRIMESTRAL = "cuatrimestral"
    ANUAL = "anual"

class EstadoSuscripcion(str, Enum):
    ACTIVA = "activa"
    PAUSADA = "pausada"
    CANCELADA = "cancelada"
    VENCIDA = "vencida"

class SuscripcionBase(BaseModel):
    """Base schema for subscription data."""
    cliente_id: str = Field(..., description="UUID del cliente")
    nombre: str = Field(..., min_length=1, max_length=100, description="Nombre de la suscripción")
    descripcion: Optional[str] = Field(None, max_length=1000, description="Descripción de la suscripción")
    precio: float = Field(..., gt=0, description="Precio por período según el tipo de suscripción")
    tipo: TipoSuscripcion = Field(..., description="Frecuencia de la suscripción")
    servicio_id: Optional[str] = Field(None, description="UUID del servicio base (opcional)")
    
    # Campos de configuración de cobro
    dia_cobro: Optional[int] = Field(None, ge=1, le=31, description="Día del mes para cobro (solo para mensual, trimestral, cuatrimestral, anual)")
    dia_cobro_semanal: Optional[int] = Field(None, ge=0, le=6, description="Día de la semana para cobro (0=Domingo, 6=Sábado) - solo para semanal")
    
    @validator('dia_cobro')
    def validate_dia_cobro(cls, v, values):
        tipo = values.get('tipo')
        if tipo == TipoSuscripcion.SEMANAL:
            # Para semanal, dia_cobro debe ser None
            if v is not None:
                raise ValueError('Para suscripciones semanales, use dia_cobro_semanal en lugar de dia_cobro')
        else:
            # Para otros tipos, dia_cobro es requerido
            if v is None:
                raise ValueError(f'dia_cobro es requerido para suscripciones {tipo}')
        return v
    
    @validator('dia_cobro_semanal')
    def validate_dia_cobro_semanal(cls, v, values):
        tipo = values.get('tipo')
        if tipo == TipoSuscripcion.SEMANAL:
            # Para semanal, dia_cobro_semanal es requerido
            if v is None:
                raise ValueError('dia_cobro_semanal es requerido para suscripciones semanales')
        else:
            # Para otros tipos, dia_cobro_semanal debe ser None
            if v is not None:
                raise ValueError('dia_cobro_semanal solo se usa para suscripciones semanales')
        return v

class SuscripcionCreate(SuscripcionBase):
    """Schema for creating a new subscription."""
    pass

class SuscripcionUpdate(BaseModel):
    """Schema for updating a subscription."""
    cliente_id: Optional[str] = Field(None, description="UUID del cliente")
    nombre: Optional[str] = Field(None, min_length=1, max_length=100, description="Nombre de la suscripción")
    descripcion: Optional[str] = Field(None, max_length=1000, description="Descripción de la suscripción")
    precio: Optional[float] = Field(None, gt=0, description="Precio por período")
    tipo: Optional[TipoSuscripcion] = Field(None, description="Frecuencia de la suscripción")
    servicio_id: Optional[str] = Field(None, description="UUID del servicio base")
    dia_cobro: Optional[int] = Field(None, ge=1, le=31, description="Día del mes para cobro")
    dia_cobro_semanal: Optional[int] = Field(None, ge=0, le=6, description="Día de la semana para cobro")
    estado: Optional[EstadoSuscripcion] = Field(None, description="Estado de la suscripción")

class Suscripcion(SuscripcionBase):
    """Schema for subscription response."""
    id: str = Field(..., description="UUID de la suscripción")
    negocio_id: str = Field(..., description="UUID del negocio")
    estado: EstadoSuscripcion = Field(default=EstadoSuscripcion.ACTIVA, description="Estado de la suscripción")
    fecha_inicio: Optional[datetime] = Field(None, description="Fecha de inicio de la suscripción")
    fecha_fin: Optional[datetime] = Field(None, description="Fecha de fin de la suscripción")
    activa: Optional[bool] = Field(None, description="Si la suscripción está activa")
    creado_en: Optional[datetime] = Field(None, description="Fecha de creación")
    actualizado_en: Optional[datetime] = Field(None, description="Fecha de última actualización")

    class Config:
        from_attributes = True 