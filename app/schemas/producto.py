from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class ProductoBase(BaseModel):
    """Base schema for product data."""
    nombre: str = Field(..., min_length=1, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=500)
    precio_compra: float = Field(..., gt=0)
    precio_venta: float = Field(..., gt=0)
    stock_actual: int = Field(..., ge=0)
    stock_minimo: int = Field(..., ge=0)
    categoria_id: str = Field(..., description="UUID de la categoría")
    codigo: Optional[str] = Field(None, max_length=50)

class ProductoCreate(ProductoBase):
    """Schema for creating a new product."""
    pass

class ProductoUpdate(BaseModel):
    """Schema for updating a product."""
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=500)
    precio_compra: Optional[float] = Field(None, gt=0)
    precio_venta: Optional[float] = Field(None, gt=0)
    stock_actual: Optional[int] = Field(None, ge=0)
    stock_minimo: Optional[int] = Field(None, ge=0)
    categoria_id: Optional[str] = Field(None, description="UUID de la categoría")
    codigo: Optional[str] = Field(None, max_length=50)
    activo: Optional[bool] = None

class Producto(ProductoBase):
    """Schema for product response."""
    id: str
    activo: bool = True
    creado_en: datetime
    actualizado_en: datetime

    class Config:
        from_attributes = True 