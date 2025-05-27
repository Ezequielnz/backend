from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

class PlanBase(BaseModel):
    nombre: str = Field(..., examples=["Básico", "Premium"])
    precio: float = Field(..., gt=0, examples=[10.00, 25.00])
    moneda: str = Field(default="USD", examples=["USD", "ARS"])
    caracteristicas: List[str] = Field(default_factory=list, examples=[["5 Proyectos", "Soporte Básico"]])
    limites: Dict[str, Any] = Field(default_factory=dict, examples=[{"max_proyectos": 5}])
    activo: bool = True
    gateway_plan_id: Optional[str] = None # ID from Stripe/MercadoPago for this plan

class PlanCreate(PlanBase):
    pass

class PlanUpdate(BaseModel): # All fields optional for update
    nombre: Optional[str] = None
    precio: Optional[float] = Field(default=None, gt=0)
    moneda: Optional[str] = None
    caracteristicas: Optional[List[str]] = None
    limites: Optional[Dict[str, Any]] = None
    activo: Optional[bool] = None
    gateway_plan_id: Optional[str] = None

class PlanResponse(PlanBase):
    id: int
    creado_en: datetime
    actualizado_en: Optional[datetime] = None

    class Config:
        from_attributes = True
