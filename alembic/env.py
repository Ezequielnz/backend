"""
Alembic environment configuration — MicroPymes Desktop
========================================================
- Lee la URL de la DB desde `app.core.config.settings.DATABASE_URL`
  (SQLite en modo desktop; puede ser PostgreSQL en desarrollo web legacy).
- Registra el `Base` de `app.models.orm_models` para que autogenerate
  detecte todas las tablas automáticamente.
- Desactiva `pool_pre_ping`, `pool_size` y `max_overflow` para SQLite
  (SQLite no los soporta en el engine de Alembic).
"""

from logging.config import fileConfig
import re

from sqlalchemy import engine_from_config, pool
from alembic import context

# ── 1. Cargar config de la app ──────────────────────────────────────────────
# Importamos settings ANTES que cualquier modelo para asegurar que las vars
# de entorno estén disponibles cuando SQLAlchemy inicialice los mappers.
from app.core.config import settings  # noqa: E402

# ── 2. Registrar todos los modelos ORM ─────────────────────────────────────
# Importar el Base con todos los modelos registrados.
from app.models.orm_models import Base  # noqa: E402, F401

# También importamos los modelos legacy por si aún están referenciados
# en endpoints que todavía no se migraron (se eliminarán en Fase 3).
try:
    from app.models.producto import Producto as _  # noqa: F401
    from app.models.servicio import Servicio as _  # noqa: F401
except ImportError:
    pass  # Modelos legacy opcionales

# ── 3. Alembic Config object ────────────────────────────────────────────────
config = context.config

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData objetivo para autogenerate
target_metadata = Base.metadata

# ── 4. Helpers ───────────────────────────────────────────────────────────────

def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _get_url() -> str:
    """
    Devuelve la URL de la DB para Alembic.

    Prioridad:
    1. Variable de entorno ALEMBIC_DB_URL (útil para CI o testing).
    2. SQLite local — modo desktop, siempre preferido sobre PostgreSQL.

    Nota: aunque settings.DATABASE_URL pueda devolver una URL de PostgreSQL
    cuando DB_PASSWORD está configurado en .env, Alembic para la versión
    desktop SIEMPRE usa SQLite.
    """
    import os
    override = os.environ.get("ALEMBIC_DB_URL")
    if override:
        return override
    # Modo desktop: SQLite local relativo al cwd (donde se invoca alembic)
    return "sqlite:///./micropymes.db"


def _engine_kwargs(url: str) -> dict:
    """
    Ajusta los kwargs del engine según el driver.
    SQLite no soporta pool_size / max_overflow → usamos StaticPool o NullPool.
    """
    if _is_sqlite(url):
        return {
            "poolclass": pool.NullPool,
        }
    return {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
    }


def _render_item(type_: str, obj, autogen_context) -> str | bool:
    """
    Hook de renderizado: hace que los Numeric() aparezcan como Float()
    en las migraciones de SQLite, que no tiene tipo NUMERIC real.
    """
    return False  # usa el renderizado por defecto


# ── 5. Modo offline (genera SQL sin conectarse) ──────────────────────────────

def run_migrations_offline() -> None:
    """
    Corre las migraciones en modo offline.
    Útil para generar el SQL y revisarlo antes de ejecutar.
    """
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite no diferencia entre NUMERIC y FLOAT — comparar sin tipo
        compare_type=True,
        render_as_batch=_is_sqlite(url),  # necesario para ALTER TABLE en SQLite
    )

    with context.begin_transaction():
        context.run_migrations()


# ── 6. Modo online (ejecuta contra la DB real) ───────────────────────────────

def run_migrations_online() -> None:
    """
    Corre las migraciones conectándose a la DB.
    """
    url = _get_url()

    # Sobreescribir la URL en la config de Alembic
    cfg_section = config.get_section(config.config_ini_section, {})
    cfg_section["sqlalchemy.url"] = url

    connectable = engine_from_config(
        cfg_section,
        prefix="sqlalchemy.",
        **_engine_kwargs(url),
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # render_as_batch es CRÍTICO para SQLite:
            # permite simular ALTER TABLE usando recreación de tabla.
            render_as_batch=_is_sqlite(url),
        )

        with context.begin_transaction():
            context.run_migrations()


# ── 7. Entry point ───────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
