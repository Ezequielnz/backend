from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class ProductoBase(BaseModel):
    """Base schema for product data."""
    nombre: str = Field(..., min_length=1, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=500)
    precio_compra: Optional[float] = Field(None, gt=0)
    precio_venta: float = Field(..., gt=0)
    stock_actual: int = Field(..., ge=0)
    stock_minimo: Optional[int] = Field(0, ge=0)
    categoria_id: Optional[str] = Field(None, description="UUID de la categoría")
    codigo: Optional[str] = Field(None, max_length=50)

class ProductoCreate(BaseModel):
    """Schema for creating a new product."""
    nombre: str = Field(..., min_length=1, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=500)
    precio_compra: Optional[float] = Field(None, gt=0)
    precio_venta: float = Field(..., gt=0)
    stock_actual: int = Field(..., ge=0)
    stock_minimo: Optional[int] = Field(0, ge=0)
    categoria_id: Optional[str] = Field(None, description="UUID de la categoría")
    codigo: Optional[str] = Field(None, max_length=50)

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
    negocio_id: str = Field(..., description="UUID del negocio")
    activo: bool = Field(default=True, description="Indica si el producto está activo")
    creado_en: datetime
    actualizado_en: datetime

    class Config:
        from_attributes = True 