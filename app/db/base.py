# Importa el Base y todos los modelos ORM para que SQLAlchemy los registre.
# Este módulo es importado por alembic/env.py y por init_db.py.
from app.models.orm_models import (  # noqa: F401
    Base,
    CategoriaFinanciera,
    Cliente,
    Compra,
    CompraDetalle,
    CuentaPendiente,
    MetodoPago,
    MovimientoFinanciero,
    Negocio,
    Producto,
    Proveedor,
    Servicio,
    StockTransfer,
    StockTransferItem,
    Tarea,
    Usuario,
    Venta,
    VentaDetalle,
    Categoria,
)