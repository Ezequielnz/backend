from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class Servicio(Base):
    id = Column(String, primary_key=True, index=True)
    negocio_id = Column(String, ForeignKey("negocios.id"), nullable=False, index=True)
    nombre = Column(String, nullable=False, index=True)
    descripcion = Column(Text, nullable=True)
    precio = Column(Float, nullable=False)
    duracion_minutos = Column(Integer, nullable=True)  # Duración estimada del servicio
    categoria_id = Column(String, ForeignKey("categorias.id"), nullable=True, index=True)
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    actualizado_en = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    negocio = relationship("Negocio", back_populates="servicios")
    categoria = relationship("Categoria", back_populates="servicios")
    suscripciones = relationship("Suscripcion", back_populates="servicio") 