from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class ProductoImportacionTemporal(BaseModel):
    """Schema para producto en importación temporal."""
    id: str
    negocio_id: str
    usuario_id: str
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    codigo: Optional[str] = None
    precio_compra: Optional[float] = None
    precio_venta: Optional[float] = None
    stock_actual: Optional[int] = None
    stock_minimo: Optional[int] = None
    categoria_nombre: Optional[str] = None
    categoria_id: Optional[str] = None
    fila_excel: int
    estado: str = "pendiente"
    errores: List[str] = Field(default_factory=list)
    datos_originales: Optional[Dict[str, Any]] = None
    confianza_nombre: float = 0.0
    confianza_precio_venta: float = 0.0
    confianza_precio_compra: float = 0.0
    confianza_stock: float = 0.0
    confianza_codigo: float = 0.0
    creado_en: datetime
    actualizado_en: datetime

    class Config:
        from_attributes = True

class ProductoImportacionUpdate(BaseModel):
    """Schema para actualizar producto en importación temporal."""
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    codigo: Optional[str] = None
    precio_compra: Optional[float] = Field(None, gt=0)
    precio_venta: Optional[float] = Field(None, gt=0)
    stock_actual: Optional[int] = Field(None, ge=0)
    stock_minimo: Optional[int] = Field(None, ge=0)
    categoria_nombre: Optional[str] = None
    categoria_id: Optional[str] = None

class ImportacionResultado(BaseModel):
    """Resultado del procesamiento de importación."""
    total_filas: int
    filas_procesadas: int
    filas_con_errores: int
    filas_validas: int
    productos_temporales: List[ProductoImportacionTemporal]
    errores_generales: List[str] = Field(default_factory=list)

class ColumnaMapeada(BaseModel):
    """Información sobre una columna mapeada del Excel."""
    nombre_original: str
    campo_mapeado: str
    confianza: float
    sugerencias: List[str] = Field(default_factory=list)

class ResumenImportacion(BaseModel):
    """Resumen de la importación para mostrar al usuario."""
    total_filas: int
    columnas_detectadas: List[ColumnaMapeada]
    productos_validos: int
    productos_con_errores: int
    productos_pendientes: int
    categorias_nuevas: List[str] = Field(default_factory=list)

class ConfirmacionImportacion(BaseModel):
    """Datos para confirmar la importación final."""
    productos_ids: List[str] = Field(..., description="IDs de productos temporales a importar")
    crear_categorias_nuevas: bool = Field(True, description="Si crear categorías que no existen")
    sobrescribir_existentes: bool = Field(False, description="Si sobrescribir productos con mismo código")

class ResultadoImportacionFinal(BaseModel):
    """Resultado de la importación final."""
    productos_creados: int
    productos_actualizados: int
    categorias_creadas: int
    errores: List[str] = Field(default_factory=list)
    productos_creados_ids: List[str] = Field(default_factory=list) 