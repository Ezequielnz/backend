from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.sql import func

from app.db.base_class import Base


class Producto(Base):
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, index=True)
    descripcion = Column(String, nullable=True)
    precio = Column(Float, nullable=False)
    stock = Column(Integer, default=0)
    codigo = Column(String, unique=True, index=True, nullable=True)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now()) 