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

class ProductoImportado(BaseModel):
    """Schema for a product detected in the PDF."""
    codigo: Optional[str] = Field(None, description="Código detectado en el PDF")
    descripcion: str = Field(..., description="Descripción extraída")
    precio_detectado: float = Field(..., description="Valor numérico del precio")
    precio_raw: Optional[str] = Field(None, description="Texto original del precio")
    pagina: int = Field(..., description="Número de página donde se encontró")

class ProductoConfirmado(BaseModel):
    """Schema for a product confirmed by the user for import."""
    codigo: Optional[str] = Field(None)
    nombre: str = Field(..., min_length=1)
    descripcion: Optional[str] = None
    precio: float = Field(..., gt=0)
    stock: int = Field(default=0, ge=0)

class ImportacionMasiva(BaseModel):
    """Schema for bulk import request."""
    productos: list[ProductoConfirmado]
    tipo_precio: str = Field(..., pattern="^(costo|venta)$", description="Indica si el precio es costo o venta") 