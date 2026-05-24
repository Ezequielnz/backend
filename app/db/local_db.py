"""
local_db.py — Capa de base de datos local (SQLAlchemy + SQLite)
================================================================
Reemplaza completamente a supabase_client.py.

Exports públicos
----------------
engine              — SQLAlchemy Engine (SQLite)
SessionLocal        — sessionmaker factory
get_db()            — FastAPI dependency que provee una Session por request
get_negocio_id()    — devuelve el UUID del único negocio instalado
check_db_connection() — health-check del DB (reemplaza check_supabase_connection)

Helpers de sesión
-----------------
Importar directamente desde este módulo evita el boilerplate de abrir/cerrar
sesiones en código que todavía no fue migrado a SQLAlchemy ORM:

    from app.db.local_db import get_db  # FastAPI Depends
    from app.db.local_db import SessionLocal  # uso directo en scripts

Notas de diseño
---------------
- SQLite siempre usa check_same_thread=False para FastAPI (multi-hilo).
- Se omite pool_size / max_overflow: SQLite usa StaticPool por defecto.
- La función get_negocio_id() es el reemplazo del "tenant scoping":
  en desktop solo hay un negocio por instalación.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. URL y engine
# ---------------------------------------------------------------------------

# Siempre SQLite en modo desktop.
# Si la variable de entorno MICROPYMES_DB_URL está definida, la usa
# (útil para testing con :memory: o rutas personalizadas).
SQLITE_URL: str = os.environ.get("MICROPYMES_DB_URL", "sqlite:///./micropymes.db")

engine = create_engine(
    SQLITE_URL,
    connect_args={"check_same_thread": False},  # necesario para FastAPI async
    echo=False,  # poner True para ver SQL en consola durante desarrollo
)

# Activa las foreign keys en cada conexión nueva (SQLite las tiene desactivadas por defecto)
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")  # mejora concurrencia de lectura
    cursor.close()


# ---------------------------------------------------------------------------
# 2. Session factory
# ---------------------------------------------------------------------------

SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # evita lazy-loads post-commit en endpoints async
)


# ---------------------------------------------------------------------------
# 3. FastAPI dependency — get_db
# ---------------------------------------------------------------------------

def get_db() -> Generator[Session, None, None]:
    """
    Dependency de FastAPI que provee una Session SQLAlchemy por request.

    Uso:
        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            return db.query(Producto).all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 4. Context manager para uso fuera de FastAPI (scripts, tareas APScheduler)
# ---------------------------------------------------------------------------

@contextmanager
def db_session() -> Generator[Session, None, None]:
    """
    Context manager para usar fuera de FastAPI (tareas en background, scripts).

    Uso:
        with db_session() as db:
            negocio = db.query(Negocio).first()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 5. Health check
# ---------------------------------------------------------------------------

def check_db_connection() -> bool:
    """
    Verifica que el archivo SQLite es accesible y responde.
    Reemplaza check_supabase_connection().
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("[local_db] Error de conexión SQLite: %s", exc)
        return False


# ---------------------------------------------------------------------------
# 6. Helpers de negocio (reemplazo del "tenant scoping" de Supabase)
# ---------------------------------------------------------------------------

def get_negocio_id(db: Session) -> str | None:
    """
    Devuelve el UUID del único negocio registrado en la instalación.

    En la versión desktop siempre hay un solo negocio. Esta función
    reemplaza el concepto de "negocio_id del usuario autenticado" que
    antes se obtenía de Supabase Auth.

    Retorna None si aún no hay negocio configurado (primer arranque).
    """
    from app.models.orm_models import Negocio  # import local para evitar ciclos

    negocio = db.query(Negocio).first()
    return negocio.id if negocio else None


def require_negocio_id(db: Session) -> str:
    """
    Como get_negocio_id() pero lanza ValueError si no hay negocio configurado.
    Usar en endpoints que no deben funcionar sin setup inicial.
    """
    negocio_id = get_negocio_id(db)
    if not negocio_id:
        raise ValueError(
            "No hay ningún negocio configurado. "
            "Complete el setup inicial antes de usar esta función."
        )
    return negocio_id


# ---------------------------------------------------------------------------
# 7. Utilidades genéricas de ORM
# ---------------------------------------------------------------------------

def get_or_404(db: Session, model, record_id: str):
    """
    Obtiene un registro por ID o lanza HTTPException 404.

    Uso:
        producto = get_or_404(db, Producto, producto_id)
    """
    from fastapi import HTTPException

    obj = db.get(model, record_id)
    if obj is None:
        raise HTTPException(
            status_code=404,
            detail=f"{model.__tablename__} con id '{record_id}' no encontrado.",
        )
    return obj


def paginate(query, skip: int = 0, limit: int = 100):
    """
    Aplica paginación a un query SQLAlchemy.

    Uso:
        items = paginate(db.query(Cliente).filter(...), skip=0, limit=20).all()
    """
    return query.offset(skip).limit(limit)


# ---------------------------------------------------------------------------
# 8. Inicialización del schema (usado en startup si no se usa Alembic)
# ---------------------------------------------------------------------------

def init_db_tables() -> None:
    """
    Crea todas las tablas definidas en orm_models.Base si no existen.
    Usar SOLO en tests o entornos donde Alembic no está configurado.
    En producción, las tablas se crean con `alembic upgrade head`.
    """
    from app.models.orm_models import Base  # import local para evitar ciclos

    Base.metadata.create_all(bind=engine)
    logger.info("[local_db] Tablas verificadas/creadas con create_all.")
