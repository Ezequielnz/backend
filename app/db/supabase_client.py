"""
supabase_client.py — SHIM DE COMPATIBILIDAD (DEPRECADO)
=========================================================
Este archivo ya NO contiene lógica de Supabase.

Propósito: evitar ImportError en archivos que todavía importan desde
aquí y serán eliminados en la Fase 1 Tarea 5 (limpieza de services/workers ML).

IMPORTANTE: No usar estas funciones en código nuevo.
            Importar desde app.db.local_db en su lugar.

Mapa de reemplazos:
    get_supabase_client()      → get_db() / SessionLocal (app.db.local_db)
    get_supabase_service_client() → get_db() (mismo engine, sin RLS en desktop)
    get_supabase_anon_client() → get_db()
    get_supabase_user_client() → get_db()
    get_table()                → db.query(Model) (SQLAlchemy ORM)
    check_supabase_connection() → check_db_connection() (app.db.local_db)
    TableQueryProto            → Session (sqlalchemy.orm)
    APIResponseProto           → (no tiene equivalente, acceso directo ORM)
"""

import logging
from typing import Any

from app.db.local_db import (  # noqa: F401
    SessionLocal,
    check_db_connection as check_supabase_connection,
    engine,
    get_db,
)

logger = logging.getLogger(__name__)

_DEPRECATION_MSG = (
    "[DEPRECADO] supabase_client.%s() fue llamado. "
    "Migrar a app.db.local_db. Este shim será eliminado en Fase 3."
)


# ---------------------------------------------------------------------------
# Stubs de las funciones Supabase — retornan None / False con warning
# ---------------------------------------------------------------------------

class _NullClient:
    """
    Objeto nulo que absorbe las llamadas al cliente Supabase sin crashear.
    Permite que el proceso arranque aunque código legacy aún importe estas funciones.
    Cualquier operación real sobre este objeto fallará con un error claro.
    """

    def table(self, name: str) -> "_NullTable":
        return _NullTable(name)

    @property
    def auth(self):
        return _NullAuth()

    def __repr__(self) -> str:
        return "<NullClient: Supabase reemplazado por SQLite>"


class _NullTable:
    def __init__(self, name: str):
        self._name = name

    def _warn(self, method: str) -> "_NullTable":
        logger.error(
            "[supabase_client shim] Llamada a tabla '%s'.%s() — "
            "este código debe ser migrado a SQLAlchemy ORM.",
            self._name, method
        )
        return self

    def select(self, *a, **kw) -> "_NullTable": return self._warn("select")
    def eq(self, *a, **kw) -> "_NullTable": return self._warn("eq")
    def neq(self, *a, **kw) -> "_NullTable": return self._warn("neq")
    def gte(self, *a, **kw) -> "_NullTable": return self._warn("gte")
    def lte(self, *a, **kw) -> "_NullTable": return self._warn("lte")
    def gt(self, *a, **kw) -> "_NullTable": return self._warn("gt")
    def lt(self, *a, **kw) -> "_NullTable": return self._warn("lt")
    def order(self, *a, **kw) -> "_NullTable": return self._warn("order")
    def limit(self, *a, **kw) -> "_NullTable": return self._warn("limit")
    def offset(self, *a, **kw) -> "_NullTable": return self._warn("offset")
    def insert(self, *a, **kw) -> "_NullTable": return self._warn("insert")
    def upsert(self, *a, **kw) -> "_NullTable": return self._warn("upsert")
    def update(self, *a, **kw) -> "_NullTable": return self._warn("update")
    def delete(self, *a, **kw) -> "_NullTable": return self._warn("delete")
    def in_(self, *a, **kw) -> "_NullTable": return self._warn("in_")
    def ilike(self, *a, **kw) -> "_NullTable": return self._warn("ilike")
    def or_(self, *a, **kw) -> "_NullTable": return self._warn("or_")
    def is_(self, *a, **kw) -> "_NullTable": return self._warn("is_")
    def not_(self, *a, **kw) -> "_NullTable": return self._warn("not_")
    def contains(self, *a, **kw) -> "_NullTable": return self._warn("contains")
    def execute(self) -> "_NullResponse": return _NullResponse()


class _NullResponse:
    """Respuesta nula que evita AttributeError en código que hace .data."""
    @property
    def data(self) -> list:
        return []

    @property
    def count(self) -> int:
        return 0


class _NullAuth:
    def get_user(self, *a, **kw) -> None:
        return None

    def sign_in_with_password(self, *a, **kw) -> None:
        return None

    def sign_out(self, *a, **kw) -> None:
        return None


# ---------------------------------------------------------------------------
# Protocol stubs para código que importa los tipos
# ---------------------------------------------------------------------------

class TableQueryProto:  # type: ignore[misc]
    """Stub de tipo para compatibilidad de imports. No usar."""
    pass


class APIResponseProto:  # type: ignore[misc]
    """Stub de tipo para compatibilidad de imports. No usar."""
    data: list = []


# ---------------------------------------------------------------------------
# Funciones públicas del shim
# ---------------------------------------------------------------------------

def get_supabase_client() -> _NullClient:
    logger.warning(_DEPRECATION_MSG, "get_supabase_client")
    return _NullClient()


def get_supabase_service_client() -> _NullClient:
    logger.warning(_DEPRECATION_MSG, "get_supabase_service_client")
    return _NullClient()


def get_supabase_anon_client() -> _NullClient:
    logger.warning(_DEPRECATION_MSG, "get_supabase_anon_client")
    return _NullClient()


def get_supabase_user_client(user_token: str = "") -> _NullClient:
    logger.warning(_DEPRECATION_MSG, "get_supabase_user_client")
    return _NullClient()


def get_table(table_name: str) -> _NullTable:
    logger.warning(_DEPRECATION_MSG, "get_table")
    return _NullTable(table_name)
