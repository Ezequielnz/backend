from typing import List, Optional
from pydantic import BaseModel, Field, validator
from datetime import datetime

# Import a product schema for nesting in responses.
# Assuming app.schemas.producto.Producto is the detailed product response schema.
from app.schemas.producto import Producto as ProductoSchema


class VentaDetalleBase(BaseModel):
    producto_id: int
    cantidad: int

    @validator('cantidad')
    def cantidad_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Cantidad must be positive')
        return v

class VentaDetalleCreate(VentaDetalleBase):
    precio_unitario: Optional[float] = None # If None, use current product price

class VentaDetalleResponse(VentaDetalleBase):
    id: int
    venta_id: int
    precio_unitario: float
    subtotal: float
    producto: Optional[ProductoSchema] = None # For returning product details

    class Config:
        from_attributes = True


class VentaBase(BaseModel):
    cliente_id: int
    descuento: Optional[float] = Field(default=0.0, ge=0) # Discount, default 0, must be non-negative
    # Fields from model that might be useful for creation if not auto-set
    medio_pago: Optional[str] = None
    estado: Optional[str] = "PENDIENTE" # Default state
    observaciones: Optional[str] = None


class VentaCreate(VentaBase):
    detalles: List[VentaDetalleCreate]

    @validator('detalles')
    def detalles_must_not_be_empty(cls, v):
        if not v:
            raise ValueError('Sale details (detalles) cannot be empty')
        return v

# Properties to return to client
class VentaResponse(VentaBase):
    id: int
    empleado_id: str # This should be the string UUID of the user
    fecha: datetime
    total: float # This will be the final calculated total after discount
    detalles: List[VentaDetalleResponse]
    # facturada and comprobante_id from model could be added if needed for response

    class Config:
        from_attributes = True
