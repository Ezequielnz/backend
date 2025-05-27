from typing import Optional, Dict, Any, List
from pydantic import BaseModel, EmailStr, validator, Field
from datetime import datetime

# Define the known onboarding steps for validation and progress calculation
KNOWN_ONBOARDING_STEPS = [
    "informacion_empresa", # Corresponds to filling out company details
    "configuracion_afip",  # Corresponds to filling out config_afip_json
    "configuracion_whatsapp" # Corresponds to filling out config_whatsapp_json
]

class ConfiguracionUsuarioBase(BaseModel):
    nombre_empresa: Optional[str] = None
    direccion_empresa: Optional[str] = None
    cuit_empresa: Optional[str] = None
    telefono_empresa: Optional[str] = None
    email_empresa: Optional[EmailStr] = None
    config_afip_json: Optional[Dict[str, Any]] = Field(default_factory=dict)
    config_whatsapp_json: Optional[Dict[str, Any]] = Field(default_factory=dict)

class ConfiguracionUsuarioCreate(ConfiguracionUsuarioBase):
    # usuario_id will be set by the server using current_user.id
    # onboarding_pasos_completados will be initialized by the server
    pass

class ConfiguracionUsuarioUpdate(BaseModel): # All fields are optional for update
    nombre_empresa: Optional[str] = None
    direccion_empresa: Optional[str] = None
    cuit_empresa: Optional[str] = None
    telefono_empresa: Optional[str] = None
    email_empresa: Optional[EmailStr] = None
    config_afip_json: Optional[Dict[str, Any]] = None
    config_whatsapp_json: Optional[Dict[str, Any]] = None
    # onboarding_pasos_completados is updated via a separate endpoint

class ConfiguracionUsuarioResponse(ConfiguracionUsuarioBase):
    usuario_id: str # UUID of the user
    onboarding_pasos_completados: Dict[str, bool] = Field(default_factory=dict)
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None

    class Config:
        from_attributes = True


class PasoProgresoUpdate(BaseModel):
    paso: str
    completado: bool = True # Default to marking as complete

    @validator('paso')
    def paso_must_be_known(cls, value):
        if value not in KNOWN_ONBOARDING_STEPS:
            raise ValueError(f"Invalid onboarding step. Known steps are: {', '.join(KNOWN_ONBOARDING_STEPS)}")
        return value

class OnboardingProgresoResponse(BaseModel):
    pasos_completados: Dict[str, bool] = Field(default_factory=dict)
    porcentaje_completado: float = Field(ge=0, le=100)
    todos_los_pasos: List[str] = Field(default_factory=lambda: KNOWN_ONBOARDING_STEPS)
