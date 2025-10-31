from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from supabase.client import Client  # type: ignore

from app.db.supabase_client import TableQueryProto, get_supabase_user_client

# Tables that must always be filtered by negocio_id and/or sucursal_id.
# The tuple indicates which contextual columns must be enforced.
TABLE_SCOPE_MAP: dict[str, tuple[str, ...]] = {
    "ventas": ("negocio_id", "sucursal_id"),
    "venta_detalle": ("negocio_id", "sucursal_id"),
    "compras": ("negocio_id", "sucursal_id"),
    "compras_detalle": ("negocio_id", "sucursal_id"),
    "inventario_sucursal": ("negocio_id", "sucursal_id"),
    "productos": ("negocio_id",),
    "clientes": ("negocio_id",),
    "proveedores": ("negocio_id",),
    "servicios": ("negocio_id",),
    "suscripciones": ("negocio_id",),
    "tareas": ("negocio_id",),
    "categorias": ("negocio_id",),
    "categorias_financieras": ("negocio_id",),
    "movimientos_financieros": ("negocio_id",),
    "cuentas_pendientes": ("negocio_id",),
    "cuentas_pendientes_historial": ("negocio_id",),
    "permisos_usuario_negocio": ("negocio_id",),
    "usuarios_negocios": ("negocio_id",),
    "usuarios_sucursales": ("negocio_id", "sucursal_id"),
    "sucursales": ("negocio_id",),
    "negocio_configuracion": ("negocio_id",),
    "producto_sucursal": ("negocio_id", "sucursal_id"),
    "servicio_sucursal": ("negocio_id", "sucursal_id"),
    "inventario_negocio": ("negocio_id",),
    "stock_transferencias": ("negocio_id",),
    "stock_transferencias_detalle": ("negocio_id",),
}


@dataclass
class _ScopeContext:
    business_id: str
    branch_id: Optional[str] = None


class ScopedTable:
    """Wrapper around Supabase table query builder that enforces negocio/sucursal scope on execute."""

    def __init__(self, builder: TableQueryProto, table_name: str, context: _ScopeContext) -> None:
        self._builder = builder
        self._table_name = table_name
        self._context = context
        self._filters_applied = False
        self._skip_filters = False

    # -- internal helpers -----------------------------------------------------------------------
    def _apply_scope(self) -> None:
        if self._filters_applied:
            return

        columns = TABLE_SCOPE_MAP.get(self._table_name, ())
        if not columns:
            self._filters_applied = True
            return

        if "negocio_id" in columns:
            self._builder = self._builder.eq("negocio_id", self._context.business_id)
        if "sucursal_id" in columns and self._context.branch_id:
            self._builder = self._builder.eq("sucursal_id", self._context.branch_id)

        self._filters_applied = True

    def _wrap_builder_call(self, method: Callable[..., Any], name: str, *args: Any, **kwargs: Any) -> Any:
        result = method(*args, **kwargs)
        if result is self._builder:
            # Reset so the new query step re-applies filters before execution.
            if name in {"select", "update", "delete", "upsert", "eq", "gte", "lte", "gt", "lt", "range", "order", "limit", "single", "maybe_single", "filter", "match", "not_", "ilike", "like", "is_", "neq", "in_"}:
                self._filters_applied = False
            if name in {"insert", "upsert"}:
                # Inserts should not receive automatic WHERE filters.
                self._skip_filters = True
            return self
        return result

    # -- public API -----------------------------------------------------------------------------
    def execute(self, *args: Any, **kwargs: Any) -> Any:
        if not self._skip_filters:
            self._apply_scope()
        result = self._builder.execute(*args, **kwargs)
        # Reset flags for potential re-use.
        self._filters_applied = False
        self._skip_filters = False
        return result

    def __getattr__(self, item: str) -> Any:
        attr = getattr(self._builder, item)
        if callable(attr):
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                return self._wrap_builder_call(attr, item, *args, **kwargs)

            return wrapper
        return attr


class ScopedSupabaseClient:
    """Client proxy adding automatic negocio/sucursal filters to table queries."""

    def __init__(self, client: Client, business_id: str, branch_id: Optional[str] = None) -> None:
        if not business_id:
            raise ValueError("business_id is required for scoped Supabase access")
        self._client = client
        self._context = _ScopeContext(business_id=business_id, branch_id=branch_id)

    def table(self, table_name: str) -> ScopedTable:
        builder_getter = getattr(self._client, "table")
        builder = builder_getter(table_name)
        return ScopedTable(builder, table_name, self._context)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._client, item)


def get_scoped_supabase_user_client(
    user_token: str,
    business_id: str,
    branch_id: Optional[str] = None,
) -> ScopedSupabaseClient:
    """
    Return a Supabase client that automatically scopes table operations to the provided negocio/sucursal.
    """
    base_client = get_supabase_user_client(user_token)
    return ScopedSupabaseClient(base_client, business_id, branch_id)
