from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# Propiedades compartidas
class ProductoBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    precio: float
    stock: int = 0
    codigo: Optional[str] = None
    activo: bool = True


# Propiedades para crear un Producto
class ProductoCreate(ProductoBase):
    pass


# Propiedades para actualizar un Producto
class ProductoUpdate(ProductoBase):
    nombre: Optional[str] = None
    precio: Optional[float] = None
    stock: Optional[int] = None


# Propiedades al leer desde la base de datos
class Producto(ProductoBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True 