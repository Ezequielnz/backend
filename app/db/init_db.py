from sqlalchemy.orm import Session

from app import crud, schemas
from app.db import base  # noqa: F401
from app.core.config import settings

# Importamos todas las tablas para que SQLAlchemy las cree
from app.db.base_class import Base
from app.db.session import engine


# Crear tablas en la base de datos
def init_db() -> None:
    Base.metadata.create_all(bind=engine)


# Inicializar la base de datos con datos de ejemplo
def init_db_with_data(db: Session) -> None:
    # Crear algunos productos de ejemplo
    productos = [
        schemas.ProductoCreate(
            nombre="Camiseta básica",
            descripcion="Camiseta de algodón de manga corta",
            precio=19.99,
            stock=50,
            codigo="CAM001",
        ),
        schemas.ProductoCreate(
            nombre="Pantalón vaquero",
            descripcion="Pantalón vaquero clásico",
            precio=39.99,
            stock=30,
            codigo="PAN001",
        ),
        schemas.ProductoCreate(
            nombre="Zapatillas deportivas",
            descripcion="Zapatillas para correr",
            precio=59.99,
            stock=20,
            codigo="ZAP001",
        ),
    ]
    
    for producto in productos:
        existing = crud.producto.get_by_codigo(db, codigo=producto.codigo)
        if not existing:
            crud.producto.create(db, obj_in=producto) 