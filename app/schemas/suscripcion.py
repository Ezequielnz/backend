from typing import Optional, Any
from pydantic import BaseModel, Field, validator
from datetime import datetime, date

from app.schemas.plan import PlanResponse # To nest plan details

class SuscripcionBase(BaseModel):
    plan_id: int
    # usuario_id is set by the server from current_user

class SuscripcionCreate(BaseModel): # Input from user to create a subscription
    plan_id: int
    payment_token: Optional[str] = None # Example: token from Stripe.js or Mercado Pago SDK
    # Other payment related details can be added here if needed by the gateway interaction
    # e.g., payment_method_id

class SuscripcionUpdate(BaseModel): # For internal updates, e.g., by webhooks or admin
    fecha_fin: Optional[datetime] = None
    estado: Optional[str] = None
    gateway_id: Optional[str] = None
    ultimo_pago_id: Optional[str] = None
    fecha_cancelacion: Optional[datetime] = None

    @validator('estado', pre=True, always=True)
    def estado_must_be_valid(cls, value):
        if value is None:
            return value
        valid_estados = ["activa", "cancelada", "vencida", "pendiente_pago", "error_pago"]
        if value.lower() not in valid_estados:
            raise ValueError(f"Estado must be one of {valid_estados}")
        return value.lower()

class SuscripcionResponse(SuscripcionBase):
    id: int
    usuario_id: str # UUID of the user
    fecha_inicio: datetime
    fecha_fin: datetime
    fecha_cancelacion: Optional[datetime] = None
    estado: str
    gateway_id: Optional[str] = None
    ultimo_pago_id: Optional[str] = None
    gateway_customer_id: Optional[str] = None
    plan: Optional[PlanResponse] = None # Nested plan details
    creado_en: datetime
    actualizado_en: Optional[datetime] = None

    class Config:
        from_attributes = True
