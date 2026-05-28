from pydantic import BaseModel, constr, Field
from typing import Optional
from uuid import UUID

class ConfiguracionFiscalBase(BaseModel):
    cuit: constr(min_length=11, max_length=11) # type: ignore
    razon_social: str
    punto_venta: int = Field(default=1, ge=1)
    condicion_fiscal: str = Field(pattern="^(monotributista|responsable_inscripto)$")
    ambiente: str = Field(default="homologacion", pattern="^(homologacion|produccion)$")
    habilitada: bool = False

class ConfiguracionFiscalCreate(ConfiguracionFiscalBase):
    pass

class ConfiguracionFiscalUpdate(BaseModel):
    cuit: Optional[constr(min_length=11, max_length=11)] = None # type: ignore
    razon_social: Optional[str] = None
    punto_venta: Optional[int] = Field(default=None, ge=1)
    condicion_fiscal: Optional[str] = Field(default=None, pattern="^(monotributista|responsable_inscripto)$")
    ambiente: Optional[str] = Field(default=None, pattern="^(homologacion|produccion)$")
    habilitada: Optional[bool] = None

class ConfiguracionFiscalResponse(ConfiguracionFiscalBase):
    id: UUID
    negocio_id: UUID
    cert_path: Optional[str] = None
    key_path: Optional[str] = None

    class Config:
        from_attributes = True

class AfipStatusResponse(BaseModel):
    status: str
    appserver: str
    dbserver: str
    authserver: str
    cuit: Optional[str] = None
    punto_venta: Optional[int] = None
    ultimo_comprobante_a: Optional[int] = None
    ultimo_comprobante_b: Optional[int] = None
    ultimo_comprobante_c: Optional[int] = None
