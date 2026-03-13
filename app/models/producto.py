from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.sql import func

from app.db.base_class import Base


class Producto(Base):
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, index=True)
    descripcion = Column(String, nullable=True)
    precio_compra = Column(Float, nullable=True)
    precio_venta = Column(Float, nullable=False)
    stock_actual = Column(Integer, default=0)
    stock_minimo = Column(Integer, default=0)
    categoria_id = Column(String, nullable=True)  # UUID as string
    proveedor_id = Column(String, nullable=True)  # UUID as string
    negocio_id = Column(String, nullable=True)  # UUID as string
    codigo = Column(String, unique=True, index=True, nullable=True)
    unidades = Column(String, nullable=True)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), onupdate=func.current_timestamp())