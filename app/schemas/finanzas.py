from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date
from decimal import Decimal

# Categoria Financiera Schemas
class CategoriaFinancieraBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    descripcion: Optional[str] = None
    tipo: str = Field(..., pattern="^(ingreso|egreso)$")
    activo: bool = True

class CategoriaFinancieraCreate(CategoriaFinancieraBase):
    pass

class CategoriaFinancieraUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    descripcion: Optional[str] = None
    activo: Optional[bool] = None

class CategoriaFinanciera(CategoriaFinancieraBase):
    id: str
    negocio_id: str
    creado_en: datetime
    actualizado_en: datetime
    creado_por: Optional[str] = None

    class Config:
        from_attributes = True

# Movimiento Financiero Schemas
class MovimientoFinancieroBase(BaseModel):
    tipo: str = Field(..., pattern="^(ingreso|egreso)$")
    categoria_id: Optional[str] = None
    monto: Decimal = Field(..., gt=0)
    fecha: date
    metodo_pago: str = Field(..., min_length=1, max_length=50)
    descripcion: Optional[str] = None
    observaciones: Optional[str] = None
    cliente_id: Optional[str] = None
    venta_id: Optional[str] = None

class MovimientoFinancieroCreate(MovimientoFinancieroBase):
    pass

class MovimientoFinancieroUpdate(BaseModel):
    categoria_id: Optional[str] = None
    monto: Optional[Decimal] = Field(None, gt=0)
    fecha: Optional[date] = None
    metodo_pago: Optional[str] = Field(None, min_length=1, max_length=50)
    descripcion: Optional[str] = None
    observaciones: Optional[str] = None
    cliente_id: Optional[str] = None

class MovimientoFinanciero(MovimientoFinancieroBase):
    id: str
    negocio_id: str
    creado_en: datetime
    actualizado_en: datetime
    creado_por: Optional[str] = None

    class Config:
        from_attributes = True

# Cuenta Pendiente Schemas
class CuentaPendienteBase(BaseModel):
    tipo: str = Field(..., pattern="^(por_cobrar|por_pagar)$")
    cliente_id: Optional[str] = None
    proveedor_nombre: Optional[str] = Field(None, max_length=200)
    monto: Decimal = Field(..., gt=0)
    fecha_vencimiento: date
    fecha_emision: date = Field(default_factory=lambda: date.today())
    estado: str = Field(default="pendiente", pattern="^(pendiente|pagado|vencido)$")
    descripcion: str = Field(..., min_length=1)
    observaciones: Optional[str] = None
    venta_id: Optional[str] = None

class CuentaPendienteCreate(CuentaPendienteBase):
    pass

class CuentaPendienteUpdate(BaseModel):
    cliente_id: Optional[str] = None
    proveedor_nombre: Optional[str] = Field(None, max_length=200)
    monto: Optional[Decimal] = Field(None, gt=0)
    fecha_vencimiento: Optional[date] = None
    estado: Optional[str] = Field(None, pattern="^(pendiente|pagado|vencido)$")
    descripcion: Optional[str] = Field(None, min_length=1)
    observaciones: Optional[str] = None

class CuentaPendiente(CuentaPendienteBase):
    id: str
    negocio_id: str
    movimiento_id: Optional[str] = None
    creado_en: datetime
    actualizado_en: datetime
    creado_por: Optional[str] = None
    pagado_en: Optional[datetime] = None
    pagado_por: Optional[str] = None

    class Config:
        from_attributes = True

# Dashboard Schemas
class ResumenFinanciero(BaseModel):
    ingresos_mes: float
    egresos_mes: float
    saldo_actual: float
    ingresos_mes_anterior: float
    egresos_mes_anterior: float

class FlujoCajaDiario(BaseModel):
    fecha: date
    ingresos: Decimal
    egresos: Decimal
    saldo_acumulado: Decimal

class FlujoCajaMensual(BaseModel):
    mes: int
    anio: int
    flujo_diario: List[FlujoCajaDiario]

# Response schemas with additional data
class MovimientoFinancieroConCategoria(MovimientoFinanciero):
    categoria_nombre: Optional[str] = None
    cliente_nombre: Optional[str] = None

class CuentaPendienteConCliente(CuentaPendiente):
    cliente_nombre: Optional[str] = None
    dias_vencimiento: Optional[int] = None
