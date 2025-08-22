from typing import Optional
from pydantic import BaseModel, Field


class TenantSettingsBase(BaseModel):
    locale: Optional[str] = Field(None, description="Locale code, e.g. 'es-AR'")
    timezone: Optional[str] = Field(None, description="Timezone name, e.g. 'America/Argentina/Buenos_Aires'")
    currency: Optional[str] = Field(None, description="Currency code, e.g. 'ARS'")
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
