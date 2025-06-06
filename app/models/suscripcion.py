from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

from app.db.base_class import Base


class TipoSuscripcion(enum.Enum):
    MENSUAL = "mensual"
    TRIMESTRAL = "trimestral"
    SEMESTRAL = "semestral"
    ANUAL = "anual"


class EstadoSuscripcion(enum.Enum):
    ACTIVA = "activa"
    PAUSADA = "pausada"
    CANCELADA = "cancelada"
    VENCIDA = "vencida"


class Suscripcion(Base):
    id = Column(String, primary_key=True, index=True)
    negocio_id = Column(String, ForeignKey("negocios.id"), nullable=False, index=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False, index=True)
    servicio_id = Column(String, ForeignKey("servicios.id"), nullable=False, index=True)
    nombre = Column(String, nullable=False)  # Nombre del plan de suscripción
    descripcion = Column(Text, nullable=True)
    precio_mensual = Column(Float, nullable=False)
    tipo = Column(Enum(TipoSuscripcion), nullable=False, default=TipoSuscripcion.MENSUAL)
    estado = Column(Enum(EstadoSuscripcion), nullable=False, default=EstadoSuscripcion.ACTIVA)
    fecha_inicio = Column(DateTime(timezone=True), nullable=False)
    fecha_fin = Column(DateTime(timezone=True), nullable=True)
    fecha_proximo_pago = Column(DateTime(timezone=True), nullable=True)
    activa = Column(Boolean, default=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    actualizado_en = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    negocio = relationship("Negocio", back_populates="suscripciones")
    cliente = relationship("Cliente", back_populates="suscripciones")
    servicio = relationship("Servicio", back_populates="suscripciones") 