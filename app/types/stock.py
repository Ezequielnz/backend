from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from .common import TimeStampMixin

class StockMovement(BaseModel):
    """Base schema for stock movements."""
    id_producto: int
    cantidad: int
    tipo_movimiento: str  # 'entrada' o 'salida'
    motivo: str
    referencia: Optional[str] = None

class StockMovementCreate(StockMovement):
    """Schema for creating a new stock movement."""
    pass

class StockMovementResponse(StockMovement, TimeStampMixin):
    """Schema for stock movement response."""
    id_movimiento: int
    usuario_id: int

    class Config:
        from_attributes = True

class StockAlert(BaseModel):
    """Schema for stock alerts."""
    id_producto: int
    nombre_producto: str
    stock_actual: int
    stock_minimo: int
    diferencia: int
    alerta_tipo: str  # 'bajo' o 'agotado' 