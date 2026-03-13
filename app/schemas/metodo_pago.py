from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class MetodoPagoBase(BaseModel):
    nombre: str
    descuento_porcentaje: float = 0
    activo: bool = True

class MetodoPagoCreate(MetodoPagoBase):
    pass

class MetodoPagoUpdate(MetodoPagoBase):
    nombre: Optional[str] = None
    descuento_porcentaje: Optional[float] = None
    activo: Optional[bool] = None

class MetodoPagoResponse(MetodoPagoBase):
    id: int
    negocio_id: str
    creado_en: Optional[datetime]
    actualizado_en: Optional[datetime]

    class Config:
        from_attributes = True
