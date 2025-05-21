from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# Propiedades compartidas
class ProductoBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    precio_compra: Optional[float] = None
    precio_venta: float
    stock_actual: int = 0
    stock_minimo: int = 0
    codigo: Optional[str] = None
    categoria_id: Optional[int] = None
    activo: bool = True


# Propiedades para crear un Producto
class ProductoCreate(ProductoBase):
    pass


# Propiedades para actualizar un Producto
class ProductoUpdate(ProductoBase):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    precio_compra: Optional[float] = None
    precio_venta: Optional[float] = None
    stock_actual: Optional[int] = None
    stock_minimo: Optional[int] = None
    categoria_id: Optional[int] = None


# Propiedades al leer desde la base de datos
class Producto(ProductoBase):
    id: int
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None

    class Config:
        from_attributes = True 