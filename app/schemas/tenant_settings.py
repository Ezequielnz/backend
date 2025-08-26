from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class RubroEnum(str, Enum):
    GENERAL = "general"
    RESTAURANTE = "restaurante"
    RETAIL = "retail"
    SERVICIOS = "servicios"
    MANUFACTURA = "manufactura"
    CONSTRUCCION = "construccion"
    SALUD = "salud"
    EDUCACION = "educacion"
    TECNOLOGIA = "tecnologia"
    TRANSPORTE = "transporte"


class TenantSettingsBase(BaseModel):
    locale: Optional[str] = Field(None, description="Locale code, e.g. 'es-AR'")
    timezone: Optional[str] = Field(None, description="Timezone name, e.g. 'America/Argentina/Buenos_Aires'")
    currency: Optional[str] = Field(None, description="Currency code, e.g. 'ARS'")
    rubro: Optional[RubroEnum] = Field(None, description="Business sector/industry")
    sales_drop_threshold: Optional[float] = Field(
        None,
        description="Numeric threshold used to detect sales drop alerts"
    )
    min_days_for_model: Optional[int] = Field(
        None,
        description="Min number of days required to train forecasting models"
    )


class TenantSettingsCreate(TenantSettingsBase):
    pass


class TenantSettingsUpdate(TenantSettingsBase):
    pass


class TenantSettings(TenantSettingsBase):
    tenant_id: str

    class Config:
        from_attributes = True
