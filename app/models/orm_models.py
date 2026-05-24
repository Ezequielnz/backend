"""
ORM Models — SQLAlchemy (SQLite)
=================================
Cada clase mapea 1:1 con una tabla de la base de datos local.

Notas de diseño:
- PKs: String (UUID) generados por Python con uuid4().
  SQLite no tiene tipo UUID nativo; guardamos como TEXT.
- Timestamps: server_default=func.now(), onupdate=func.now()
- negocio_id: en la versión desktop es siempre el mismo (un solo negocio
  por instalación), pero se conserva para mantener compatibilidad con los
  schemas y endpoints existentes.
- Todas las relaciones usan lazy="select" (default) para simplicidad.
  Cambiar a lazy="joined" si se detectan N+1 en el futuro.
"""

import uuid
from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, relationship


# ---------------------------------------------------------------------------
# Base declarativa
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    """Genera un UUID v4 como string. Usado como default en PKs."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# 1. Negocio
# ---------------------------------------------------------------------------

class Negocio(Base):
    """Empresa / negocio dueño de la instalación."""

    __tablename__ = "negocios"

    id: str = Column(String, primary_key=True, default=_uuid)
    nombre: str = Column(String(200), nullable=False)
    descripcion: str = Column(Text, nullable=True)
    direccion: str = Column(String(300), nullable=True)
    telefono: str = Column(String(50), nullable=True)
    email: str = Column(String(150), nullable=True)
    logo_url: str = Column(String(500), nullable=True)
    # Campo para guardar la API key de OpenAI (se leerá del keychain en producción)
    openai_api_key: str = Column(String(200), nullable=True)
    creado_en: datetime = Column(DateTime, server_default=func.now(), nullable=False)
    actualizado_en: datetime = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relaciones
    usuarios = relationship("Usuario", back_populates="negocio", cascade="all, delete-orphan")
    categorias = relationship("Categoria", back_populates="negocio", cascade="all, delete-orphan")
    categorias_financieras = relationship("CategoriaFinanciera", back_populates="negocio", cascade="all, delete-orphan")
    metodos_pago = relationship("MetodoPago", back_populates="negocio", cascade="all, delete-orphan")
    clientes = relationship("Cliente", back_populates="negocio", cascade="all, delete-orphan")
    proveedores = relationship("Proveedor", back_populates="negocio", cascade="all, delete-orphan")
    productos = relationship("Producto", back_populates="negocio", cascade="all, delete-orphan")
    servicios = relationship("Servicio", back_populates="negocio", cascade="all, delete-orphan")
    ventas = relationship("Venta", back_populates="negocio", cascade="all, delete-orphan")
    compras = relationship("Compra", back_populates="negocio", cascade="all, delete-orphan")
    tareas = relationship("Tarea", back_populates="negocio", cascade="all, delete-orphan")
    movimientos_financieros = relationship("MovimientoFinanciero", back_populates="negocio", cascade="all, delete-orphan")
    cuentas_pendientes = relationship("CuentaPendiente", back_populates="negocio", cascade="all, delete-orphan")
    stock_transfers = relationship("StockTransfer", back_populates="negocio", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# 2. Usuario
# ---------------------------------------------------------------------------

class Usuario(Base):
    """Usuario del sistema (único en la versión desktop)."""

    __tablename__ = "usuarios"

    id: str = Column(String, primary_key=True, default=_uuid)
    negocio_id: str = Column(String, ForeignKey("negocios.id", ondelete="CASCADE"), nullable=False)
    email: str = Column(String(150), nullable=False, unique=True, index=True)
    nombre: str = Column(String(100), nullable=False)
    apellido: str = Column(String(100), nullable=False)
    hashed_password: str = Column(String(200), nullable=False)
    is_active: bool = Column(Boolean, default=True, nullable=False)
    is_superuser: bool = Column(Boolean, default=False, nullable=False)
    onboarding_completed: bool = Column(Boolean, default=False, nullable=False)
    creado_en: datetime = Column(DateTime, server_default=func.now(), nullable=False)
    fecha_actualizacion: datetime = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    ultimo_acceso: datetime = Column(DateTime, nullable=True)

    # Relaciones
    negocio = relationship("Negocio", back_populates="usuarios")
    tareas_asignadas = relationship("Tarea", foreign_keys="Tarea.asignada_a_id", back_populates="asignado_a")
    tareas_creadas = relationship("Tarea", foreign_keys="Tarea.creada_por_id", back_populates="creado_por")


# ---------------------------------------------------------------------------
# 3. Categoria  (para productos y servicios)
# ---------------------------------------------------------------------------

class Categoria(Base):
    """Categoría de productos o servicios."""

    __tablename__ = "categorias"

    id: str = Column(String, primary_key=True, default=_uuid)
    negocio_id: str = Column(String, ForeignKey("negocios.id", ondelete="CASCADE"), nullable=False)
    nombre: str = Column(String(100), nullable=False)
    descripcion: str = Column(Text, nullable=True)
    created_at: datetime = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at: datetime = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relaciones
    negocio = relationship("Negocio", back_populates="categorias")
    productos = relationship("Producto", back_populates="categoria")
    servicios = relationship("Servicio", back_populates="categoria")


# ---------------------------------------------------------------------------
# 4. MetodoPago
# ---------------------------------------------------------------------------

class MetodoPago(Base):
    """Método de pago disponible para ventas."""

    __tablename__ = "metodos_pago"

    id: str = Column(String, primary_key=True, default=_uuid)
    negocio_id: str = Column(String, ForeignKey("negocios.id", ondelete="CASCADE"), nullable=False)
    nombre: str = Column(String(100), nullable=False)
    descuento_porcentaje: float = Column(Float, default=0.0, nullable=False)
    activo: bool = Column(Boolean, default=True, nullable=False)
    creado_en: datetime = Column(DateTime, server_default=func.now(), nullable=True)
    actualizado_en: datetime = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relaciones
    negocio = relationship("Negocio", back_populates="metodos_pago")


# ---------------------------------------------------------------------------
# 5. Proveedor
# ---------------------------------------------------------------------------

class Proveedor(Base):
    """Proveedor de productos."""

    __tablename__ = "proveedores"

    id: str = Column(String, primary_key=True, default=_uuid)
    negocio_id: str = Column(String, ForeignKey("negocios.id", ondelete="CASCADE"), nullable=False)
    nombre: str = Column(String(200), nullable=False)
    cuit_cuil: str = Column(String(20), nullable=True)
    email: str = Column(String(150), nullable=True)
    telefono: str = Column(String(50), nullable=True)
    direccion: str = Column(String(300), nullable=True)
    ciudad: str = Column(String(100), nullable=True)
    provincia: str = Column(String(100), nullable=True)
    pais: str = Column(String(100), nullable=True)
    condiciones_pago: str = Column(String(200), nullable=True)
    observaciones: str = Column(Text, nullable=True)
    estado: str = Column(String(50), nullable=True, default="activo")
    creado_en: datetime = Column(DateTime, server_default=func.now(), nullable=True)
    actualizado_en: datetime = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relaciones
    negocio = relationship("Negocio", back_populates="proveedores")
    productos = relationship("Producto", back_populates="proveedor")
    compras = relationship("Compra", back_populates="proveedor")


# ---------------------------------------------------------------------------
# 6. Cliente
# ---------------------------------------------------------------------------

class Cliente(Base):
    """Cliente del negocio."""

    __tablename__ = "clientes"

    id: str = Column(String, primary_key=True, default=_uuid)
    negocio_id: str = Column(String, ForeignKey("negocios.id", ondelete="CASCADE"), nullable=False)
    nombre: str = Column(String(100), nullable=False)
    apellido: str = Column(String(100), nullable=False)
    documento_tipo: str = Column(String(20), nullable=True)
    documento_numero: str = Column(String(20), nullable=True)
    email: str = Column(String(150), nullable=True)
    telefono: str = Column(String(50), nullable=True)
    direccion: str = Column(String(200), nullable=True)
    creado_en: datetime = Column(DateTime, server_default=func.now(), nullable=True)
    actualizado_en: datetime = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relaciones
    negocio = relationship("Negocio", back_populates="clientes")
    ventas = relationship("Venta", back_populates="cliente")
    movimientos_financieros = relationship("MovimientoFinanciero", back_populates="cliente")
    cuentas_pendientes = relationship("CuentaPendiente", back_populates="cliente")


# ---------------------------------------------------------------------------
# 7. Producto
# ---------------------------------------------------------------------------

class Producto(Base):
    """Producto del catálogo del negocio."""

    __tablename__ = "productos"

    id: str = Column(String, primary_key=True, default=_uuid)
    negocio_id: str = Column(String, ForeignKey("negocios.id", ondelete="CASCADE"), nullable=False)
    codigo: str = Column(String(50), nullable=True, index=True)
    nombre: str = Column(String(200), nullable=False)
    descripcion: str = Column(Text, nullable=True)
    precio_compra: float = Column(Float, nullable=True)
    precio_venta: float = Column(Float, nullable=False)
    stock_actual: int = Column(Integer, default=0, nullable=False)
    stock_minimo: int = Column(Integer, default=0, nullable=True)
    unidades: str = Column(String(50), nullable=True)
    categoria_id: str = Column(String, ForeignKey("categorias.id", ondelete="SET NULL"), nullable=True)
    proveedor_id: str = Column(String, ForeignKey("proveedores.id", ondelete="SET NULL"), nullable=True)
    activo: bool = Column(Boolean, default=True, nullable=False)
    creado_en: datetime = Column(DateTime, server_default=func.now(), nullable=False)
    actualizado_en: datetime = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relaciones
    negocio = relationship("Negocio", back_populates="productos")
    categoria = relationship("Categoria", back_populates="productos")
    proveedor = relationship("Proveedor", back_populates="productos")
    venta_detalles = relationship("VentaDetalle", back_populates="producto")
    compra_detalles = relationship("CompraDetalle", back_populates="producto")
    stock_transfer_items = relationship("StockTransferItem", back_populates="producto")


# ---------------------------------------------------------------------------
# 8. Servicio
# ---------------------------------------------------------------------------

class Servicio(Base):
    """Servicio ofrecido por el negocio."""

    __tablename__ = "servicios"

    id: str = Column(String, primary_key=True, default=_uuid)
    negocio_id: str = Column(String, ForeignKey("negocios.id", ondelete="CASCADE"), nullable=False)
    nombre: str = Column(String(200), nullable=False)
    descripcion: str = Column(Text, nullable=True)
    precio: float = Column(Float, nullable=False)
    duracion_minutos: int = Column(Integer, nullable=True)
    tipo: str = Column(String(50), nullable=True, default="mensual")
    categoria_id: str = Column(String, ForeignKey("categorias.id", ondelete="SET NULL"), nullable=True)
    activo: bool = Column(Boolean, default=True, nullable=False)
    creado_en: datetime = Column(DateTime, server_default=func.now(), nullable=False)
    actualizado_en: datetime = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relaciones
    negocio = relationship("Negocio", back_populates="servicios")
    categoria = relationship("Categoria", back_populates="servicios")


# ---------------------------------------------------------------------------
# 9. Venta
# ---------------------------------------------------------------------------

class Venta(Base):
    """Encabezado de una venta."""

    __tablename__ = "ventas"

    id: str = Column(String, primary_key=True, default=_uuid)
    negocio_id: str = Column(String, ForeignKey("negocios.id", ondelete="CASCADE"), nullable=False)
    cliente_id: str = Column(String, ForeignKey("clientes.id", ondelete="SET NULL"), nullable=True)
    usuario_id: str = Column(String, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    fecha: datetime = Column(DateTime, server_default=func.now(), nullable=False)
    total: float = Column(Float, nullable=False, default=0.0)
    descuento_total: float = Column(Float, nullable=True, default=0.0)
    metodo_pago: str = Column(String(100), nullable=True)
    metodo_pago_id: str = Column(String, ForeignKey("metodos_pago.id", ondelete="SET NULL"), nullable=True)
    estado: str = Column(String(50), nullable=False, default="completada")
    observaciones: str = Column(Text, nullable=True)
    creado_en: datetime = Column(DateTime, server_default=func.now(), nullable=False)
    actualizado_en: datetime = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relaciones
    negocio = relationship("Negocio", back_populates="ventas")
    cliente = relationship("Cliente", back_populates="ventas")
    detalles = relationship("VentaDetalle", back_populates="venta", cascade="all, delete-orphan")
    movimientos_financieros = relationship("MovimientoFinanciero", back_populates="venta")
    cuentas_pendientes = relationship("CuentaPendiente", back_populates="venta")


# ---------------------------------------------------------------------------
# 10. VentaDetalle
# ---------------------------------------------------------------------------

class VentaDetalle(Base):
    """Línea de detalle de una venta (producto o servicio)."""

    __tablename__ = "venta_detalle"

    id: str = Column(String, primary_key=True, default=_uuid)
    venta_id: str = Column(String, ForeignKey("ventas.id", ondelete="CASCADE"), nullable=False)
    negocio_id: str = Column(String, nullable=False)  # Denormalizado para consultas rápidas
    producto_id: str = Column(String, ForeignKey("productos.id", ondelete="SET NULL"), nullable=True)
    servicio_id: str = Column(String, ForeignKey("servicios.id", ondelete="SET NULL"), nullable=True)
    descripcion: str = Column(String(300), nullable=True)  # Snapshot del nombre al momento de la venta
    cantidad: float = Column(Float, nullable=False, default=1)
    precio_unitario: float = Column(Float, nullable=False)
    descuento: float = Column(Float, nullable=True, default=0.0)
    subtotal: float = Column(Float, nullable=False)

    # Relaciones
    venta = relationship("Venta", back_populates="detalles")
    producto = relationship("Producto", back_populates="venta_detalles")
    servicio = relationship("Servicio")


# ---------------------------------------------------------------------------
# 11. Compra
# ---------------------------------------------------------------------------

class Compra(Base):
    """Encabezado de una compra a proveedor."""

    __tablename__ = "compras"

    id: str = Column(String, primary_key=True, default=_uuid)
    negocio_id: str = Column(String, ForeignKey("negocios.id", ondelete="CASCADE"), nullable=False)
    proveedor_id: str = Column(String, ForeignKey("proveedores.id", ondelete="SET NULL"), nullable=True)
    proveedor_nombre: str = Column(String(200), nullable=True)  # Nombre libre si no hay registro
    usuario_id: str = Column(String, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    fecha: date = Column(Date, nullable=True)
    fecha_entrega: date = Column(Date, nullable=True)
    metodo_pago: str = Column(String(100), nullable=True)
    estado: str = Column(String(50), nullable=True, default="entregado")
    total: float = Column(Float, nullable=False, default=0.0)
    observaciones: str = Column(Text, nullable=True)
    creado_en: datetime = Column(DateTime, server_default=func.now(), nullable=False)
    actualizado_en: datetime = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relaciones
    negocio = relationship("Negocio", back_populates="compras")
    proveedor = relationship("Proveedor", back_populates="compras")
    detalles = relationship("CompraDetalle", back_populates="compra", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# 12. CompraDetalle
# ---------------------------------------------------------------------------

class CompraDetalle(Base):
    """Línea de detalle de una compra."""

    __tablename__ = "compras_detalle"

    id: str = Column(String, primary_key=True, default=_uuid)
    compra_id: str = Column(String, ForeignKey("compras.id", ondelete="CASCADE"), nullable=False)
    negocio_id: str = Column(String, nullable=False)  # Denormalizado
    producto_id: str = Column(String, ForeignKey("productos.id", ondelete="SET NULL"), nullable=True)
    descripcion: str = Column(String(300), nullable=True)  # Snapshot nombre producto
    cantidad: float = Column(Float, nullable=False)
    precio_unitario: float = Column(Float, nullable=False)
    subtotal: float = Column(Float, nullable=False)

    # Relaciones
    compra = relationship("Compra", back_populates="detalles")
    producto = relationship("Producto", back_populates="compra_detalles")


# ---------------------------------------------------------------------------
# 13. StockTransfer  (transferencia de stock entre ubicaciones)
# ---------------------------------------------------------------------------

class StockTransfer(Base):
    """Cabecera de una transferencia de stock."""

    __tablename__ = "transferencias_stock"

    id: str = Column(String, primary_key=True, default=_uuid)
    negocio_id: str = Column(String, ForeignKey("negocios.id", ondelete="CASCADE"), nullable=False)
    # En la versión desktop con un solo negocio, origen/destino pueden ser
    # ubicaciones lógicas o almacenes. Se conserva la estructura para futura extensión.
    origen_ubicacion: str = Column(String(200), nullable=True)
    destino_ubicacion: str = Column(String(200), nullable=True)
    estado: str = Column(String(50), nullable=False, default="confirmada")
    comentarios: str = Column(Text, nullable=True)
    creado_por_id: str = Column(String, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    aprobado_por_id: str = Column(String, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    created_at: datetime = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at: datetime = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relaciones
    negocio = relationship("Negocio", back_populates="stock_transfers")
    items = relationship("StockTransferItem", back_populates="transfer", cascade="all, delete-orphan")


class StockTransferItem(Base):
    """Línea de detalle de una transferencia de stock."""

    __tablename__ = "transferencias_stock_items"

    id: str = Column(String, primary_key=True, default=_uuid)
    transferencia_id: str = Column(String, ForeignKey("transferencias_stock.id", ondelete="CASCADE"), nullable=False)
    negocio_id: str = Column(String, nullable=False)  # Denormalizado
    producto_id: str = Column(String, ForeignKey("productos.id", ondelete="SET NULL"), nullable=True)
    cantidad: float = Column(Float, nullable=False)
    unidad: str = Column(String(50), nullable=True)
    lote: str = Column(String(100), nullable=True)
    created_at: datetime = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at: datetime = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relaciones
    transfer = relationship("StockTransfer", back_populates="items")
    producto = relationship("Producto", back_populates="stock_transfer_items")


# ---------------------------------------------------------------------------
# 14. Tarea
# ---------------------------------------------------------------------------

class Tarea(Base):
    """Tarea interna del negocio."""

    __tablename__ = "tareas"

    id: str = Column(String, primary_key=True, default=_uuid)
    negocio_id: str = Column(String, ForeignKey("negocios.id", ondelete="CASCADE"), nullable=False)
    titulo: str = Column(String(200), nullable=False)
    descripcion: str = Column(Text, nullable=True)
    fecha_inicio: datetime = Column(DateTime, nullable=True)
    fecha_fin: datetime = Column(DateTime, nullable=True)
    estado: str = Column(String(50), nullable=False, default="pendiente")
    prioridad: str = Column(String(50), nullable=False, default="media")
    asignada_a_id: str = Column(String, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    creada_por_id: str = Column(String, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    creado_en: datetime = Column(DateTime, server_default=func.now(), nullable=True)
    actualizado_en: datetime = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relaciones
    negocio = relationship("Negocio", back_populates="tareas")
    asignado_a = relationship("Usuario", foreign_keys=[asignada_a_id], back_populates="tareas_asignadas")
    creado_por = relationship("Usuario", foreign_keys=[creada_por_id], back_populates="tareas_creadas")


# ---------------------------------------------------------------------------
# 15. CategoriaFinanciera
# ---------------------------------------------------------------------------

class CategoriaFinanciera(Base):
    """Categoría para clasificar movimientos financieros."""

    __tablename__ = "categorias_financieras"

    id: str = Column(String, primary_key=True, default=_uuid)
    negocio_id: str = Column(String, ForeignKey("negocios.id", ondelete="CASCADE"), nullable=False)
    nombre: str = Column(String(100), nullable=False)
    descripcion: str = Column(Text, nullable=True)
    tipo: str = Column(String(20), nullable=False)  # 'ingreso' | 'egreso'
    activo: bool = Column(Boolean, default=True, nullable=False)
    creado_en: datetime = Column(DateTime, server_default=func.now(), nullable=False)
    actualizado_en: datetime = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    creado_por: str = Column(String, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)

    # Relaciones
    negocio = relationship("Negocio", back_populates="categorias_financieras")
    movimientos = relationship("MovimientoFinanciero", back_populates="categoria_financiera")


# ---------------------------------------------------------------------------
# 16. MovimientoFinanciero
# ---------------------------------------------------------------------------

class MovimientoFinanciero(Base):
    """Movimiento de ingresos o egresos del negocio."""

    __tablename__ = "movimientos_financieros"

    id: str = Column(String, primary_key=True, default=_uuid)
    negocio_id: str = Column(String, ForeignKey("negocios.id", ondelete="CASCADE"), nullable=False)
    tipo: str = Column(String(20), nullable=False)  # 'ingreso' | 'egreso'
    categoria_id: str = Column(String, ForeignKey("categorias_financieras.id", ondelete="SET NULL"), nullable=True)
    monto: float = Column(Numeric(12, 2), nullable=False)
    fecha: date = Column(Date, nullable=False)
    metodo_pago: str = Column(String(100), nullable=False)
    descripcion: str = Column(Text, nullable=True)
    observaciones: str = Column(Text, nullable=True)
    cliente_id: str = Column(String, ForeignKey("clientes.id", ondelete="SET NULL"), nullable=True)
    venta_id: str = Column(String, ForeignKey("ventas.id", ondelete="SET NULL"), nullable=True)
    creado_en: datetime = Column(DateTime, server_default=func.now(), nullable=False)
    actualizado_en: datetime = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    creado_por: str = Column(String, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)

    # Relaciones
    negocio = relationship("Negocio", back_populates="movimientos_financieros")
    categoria_financiera = relationship("CategoriaFinanciera", back_populates="movimientos")
    cliente = relationship("Cliente", back_populates="movimientos_financieros")
    venta = relationship("Venta", back_populates="movimientos_financieros")


# ---------------------------------------------------------------------------
# 17. CuentaPendiente
# ---------------------------------------------------------------------------

class CuentaPendiente(Base):
    """Cuenta por cobrar o por pagar."""

    __tablename__ = "cuentas_pendientes"

    id: str = Column(String, primary_key=True, default=_uuid)
    negocio_id: str = Column(String, ForeignKey("negocios.id", ondelete="CASCADE"), nullable=False)
    tipo: str = Column(String(20), nullable=False)  # 'por_cobrar' | 'por_pagar'
    cliente_id: str = Column(String, ForeignKey("clientes.id", ondelete="SET NULL"), nullable=True)
    proveedor_nombre: str = Column(String(200), nullable=True)
    monto: float = Column(Numeric(12, 2), nullable=False)
    fecha_vencimiento: date = Column(Date, nullable=False)
    fecha_emision: date = Column(Date, nullable=False)
    estado: str = Column(String(20), nullable=False, default="pendiente")  # pendiente | pagado | vencido
    descripcion: str = Column(Text, nullable=False)
    observaciones: str = Column(Text, nullable=True)
    venta_id: str = Column(String, ForeignKey("ventas.id", ondelete="SET NULL"), nullable=True)
    movimiento_id: str = Column(String, ForeignKey("movimientos_financieros.id", ondelete="SET NULL"), nullable=True)
    creado_en: datetime = Column(DateTime, server_default=func.now(), nullable=False)
    actualizado_en: datetime = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    creado_por: str = Column(String, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    pagado_en: datetime = Column(DateTime, nullable=True)
    pagado_por: str = Column(String, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)

    # Relaciones
    negocio = relationship("Negocio", back_populates="cuentas_pendientes")
    cliente = relationship("Cliente", back_populates="cuentas_pendientes")
    venta = relationship("Venta", back_populates="cuentas_pendientes")
