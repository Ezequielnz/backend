from typing import Dict, List, Optional, Any, TypeVar, Generic, Union
from pydantic import BaseModel, Field
from datetime import datetime

from app.db.supabase_client import get_table

# Type variable for generic model
T = TypeVar('T', bound=BaseModel)

# Base model adapter
class SupabaseModel(BaseModel):
    """Base class for all Supabase models that provides common CRUD methods."""
    
    @classmethod
    def table_name(cls) -> str:
        """
        Get the table name for this model.
        Should be overridden by subclasses.
        """
        raise NotImplementedError("Subclasses must implement table_name")
    
    @classmethod
    async def get_by_id(cls, id: int) -> Optional[Dict[str, Any]]:
        """Get a record by ID."""
        response = get_table(cls.table_name()).select("*").eq("id", id).execute()
        data = response.data
        return data[0] if data else None
    
    @classmethod
    async def get_all(cls) -> List[Dict[str, Any]]:
        """Get all records."""
        response = get_table(cls.table_name()).select("*").execute()
        return response.data
    
    @classmethod
    async def create(cls, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new record."""
        response = get_table(cls.table_name()).insert(data).execute()
        return response.data[0] if response.data else None
    
    @classmethod
    async def update(cls, id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a record by ID."""
        response = get_table(cls.table_name()).update(data).eq("id", id).execute()
        return response.data[0] if response.data else None
    
    @classmethod
    async def delete(cls, id: int) -> Optional[Dict[str, Any]]:
        """Delete a record by ID."""
        response = get_table(cls.table_name()).delete().eq("id", id).execute()
        return response.data[0] if response.data else None

# Client model
class Cliente(SupabaseModel):
    id: Optional[int] = None
    nombre: str
    apellido: str
    documento_tipo: str
    documento_numero: str
    email: str
    telefono: str
    direccion: str
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None
    
    @classmethod
    def table_name(cls) -> str:
        return "clientes"
        
# Usuario model
class Usuario(SupabaseModel):
    id: Optional[int] = None
    email: str
    nombre: str
    apellido: str
    rol: str
    permisos: Optional[List[str]] = Field(default_factory=list)
    creado_en: Optional[datetime] = None
    ultimo_acceso: Optional[datetime] = None
    subscription_status: Optional[str] = "trial"
    trial_end: Optional[datetime] = None
    is_exempt: bool = False
    
    @classmethod
    def table_name(cls) -> str:
        return "usuarios"

# Tarea model
class Tarea(SupabaseModel):
    id: Optional[int] = None
    titulo: str
    descripcion: Optional[str] = None
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    asignado_id: Optional[int] = None
    creado_por: Optional[int] = None
    estado: str
    prioridad: str
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None
    
    @classmethod
    def table_name(cls) -> str:
        return "tareas"

# Producto model
class Producto(SupabaseModel):
    id: Optional[str] = None
    negocio_id: str 
    codigo: Optional[str] = None
    nombre: str
    descripcion: Optional[str] = None
    precio_compra: Optional[float] = None
    precio_venta: float
    stock_actual: int
    stock_minimo: Optional[int] = None
    categoria_id: Optional[str] = None
    activo: bool = True
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None
    
    @classmethod
    def table_name(cls) -> str:
        return "productos"

# Categoria model
class Categoria(SupabaseModel):
    id: Optional[int] = None
    nombre: str
    descripcion: Optional[str] = None
    
    @classmethod
    def table_name(cls) -> str:
        return "categorias"

# Venta model
class Venta(SupabaseModel):
    id: Optional[int] = None
    fecha: datetime
    cliente_id: int
    empleado_id: int
    total: float
    medio_pago: str
    estado: str
    facturada: bool = False
    comprobante_id: Optional[str] = None
    observaciones: Optional[str] = None
    
    @classmethod
    def table_name(cls) -> str:
        return "ventas"

# Detalle de venta model
class VentaDetalle(SupabaseModel):
    id: Optional[int] = None
    venta_id: int
    producto_id: int
    cantidad: int
    precio_unitario: float
    subtotal: float
    descuento: Optional[float] = 0
    
    @classmethod
    def table_name(cls) -> str:
        return "venta_detalle"

# Configuración de área model
class ConfiguracionArea(SupabaseModel):
    id: Optional[int] = None
    cuit: str
    punto_venta: int
    certificado: str
    clave: str
    produccion: bool = False
    ultimo_comprobante: Optional[Dict[str, Any]] = None
    
    @classmethod
    def table_name(cls) -> str:
        return "configuracion_area"

# Finance module models
class CategoriaFinanciera(SupabaseModel):
    id: Optional[str] = None
    negocio_id: str
    nombre: str
    descripcion: Optional[str] = None
    tipo: str  # 'ingreso' or 'egreso'
    activo: bool = True
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None
    creado_por: Optional[str] = None
    
    @classmethod
    def table_name(cls) -> str:
        return "categorias_financieras"

class MovimientoFinanciero(SupabaseModel):
    id: Optional[str] = None
    negocio_id: str
    tipo: str  # 'ingreso' or 'egreso'
    categoria_id: Optional[str] = None
    monto: float
    fecha: datetime
    metodo_pago: str
    descripcion: Optional[str] = None
    observaciones: Optional[str] = None
    cliente_id: Optional[str] = None
    venta_id: Optional[str] = None
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None
    creado_por: Optional[str] = None
    
    @classmethod
    def table_name(cls) -> str:
        return "movimientos_financieros"

class CuentaPendiente(SupabaseModel):
    id: Optional[str] = None
    negocio_id: str
    tipo: str  # 'por_cobrar' or 'por_pagar'
    cliente_id: Optional[str] = None
    proveedor_nombre: Optional[str] = None
    monto: float
    fecha_vencimiento: datetime
    fecha_emision: datetime
    estado: str = "pendiente"  # 'pendiente', 'pagado', 'vencido'
    descripcion: str
    observaciones: Optional[str] = None
    venta_id: Optional[str] = None
    movimiento_id: Optional[str] = None
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None
    creado_por: Optional[str] = None
    pagado_en: Optional[datetime] = None
    pagado_por: Optional[str] = None
    
    @classmethod
    def table_name(cls) -> str:
        return "cuentas_pendientes"