from typing import List, Optional, Dict, Any
from pydantic import BaseModel, validator
from datetime import date

class ReporteQueryParams(BaseModel):
    fecha_inicio: date
    fecha_fin: date
    agrupar_por: Optional[str] = "dia"

    @validator('agrupar_por')
    def group_by_must_be_valid(cls, value):
        if value not in ['dia', 'mes']:
            raise ValueError("agrupar_por must be 'dia' or 'mes'")
        return value

    @validator('fecha_fin')
    def end_date_must_be_after_start_date(cls, v, values):
        if 'fecha_inicio' in values and v < values['fecha_inicio']:
            raise ValueError('fecha_fin must be on or after fecha_inicio')
        return v

class VentaPorPeriodo(BaseModel):
    periodo: str  # e.g., "2023-10-26" for day, "2023-10" for month
    total_ventas: float
    total_ganancia: Optional[float] = None # Profit calculation depends on precio_compra
    numero_ventas: int

class ReporteVentasResponse(BaseModel):
    resumen: List[VentaPorPeriodo]
    total_general_ventas: float
    total_general_ganancia: Optional[float] = None
    filtros: Dict[str, Any] # Echoing back applied filters like fecha_inicio, fecha_fin, agrupar_por
