from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional, Set

import pytest

from app.api.api_v1.endpoints import stock


class DummyResponse:
    def __init__(self, data: List[Dict[str, Any]]) -> None:
        self.data = data


class DummyTable:
    def __init__(self, rows: Iterable[Dict[str, Any]]) -> None:
        self.rows = [dict(row) for row in rows]
        self._reset()

    def select(self, *_fields: Any) -> "DummyTable":
        self._mode = "select"
        self._reset_filters()
        return self

    def eq(self, column: str, value: Any) -> "DummyTable":
        if self._mode == "select":
            self._filters.append((column, str(value)))
        return self

    def in_(self, column: str, values: Iterable[Any]) -> "DummyTable":
        if self._mode == "select":
            self._in_filters.append((column, {str(v) for v in values}))
        return self

    def range(self, *_args: Any) -> "DummyTable":
        return self

    def limit(self, *_args: Any) -> "DummyTable":
        return self

    def execute(self) -> DummyResponse:
        if self._mode != "select":
            return DummyResponse([])

        result: List[Dict[str, Any]] = []
        for row in self.rows:
            if not self._match(row):
                continue
            result.append(dict(row))
        self._reset_filters()
        return DummyResponse(result)

    def _match(self, row: Dict[str, Any]) -> bool:
        for column, value in self._filters:
            if str(row.get(column)) != value:
                return False
        for column, values in self._in_filters:
            if str(row.get(column)) not in values:
                return False
        return True

    def _reset(self) -> None:
        self._mode: Optional[str] = None
        self._reset_filters()

    def _reset_filters(self) -> None:
        self._filters: List[tuple[str, str]] = []
        self._in_filters: List[tuple[str, Set[str]]] = []


class DummyScopedClient:
    def __init__(self, tables: Dict[str, DummyTable]) -> None:
        self._tables = tables

    def table(self, name: str) -> DummyTable:
        return self._tables[name]


class DummyScopedContext:
    def __init__(
        self,
        client: DummyScopedClient,
        *,
        business_id: str,
        branch_id: Optional[str],
        branch_settings: Dict[str, Any],
    ) -> None:
        self.client = client
        self.context = SimpleNamespace(
            business_id=business_id,
            branch_id=branch_id,
            branch_settings=branch_settings,
        )


@pytest.mark.asyncio
async def test_get_productos_centralized_inventory() -> None:
    tables = {
        "productos": DummyTable(
            [
                {"id": "prod-1", "negocio_id": "biz-1", "nombre": "Prod Central", "activo": True, "stock_actual": 0},
            ]
        ),
        "inventario_negocio": DummyTable(
            [
                {"producto_id": "prod-1", "stock_total": 12},
            ]
        ),
        "inventario_sucursal": DummyTable([]),
        "producto_sucursal": DummyTable([]),
    }
    client = DummyScopedClient(tables)
    settings = {
        "inventario_modo": "centralizado",
        "catalogo_producto_modo": "compartido",
    }
    scoped = DummyScopedContext(client, business_id="biz-1", branch_id=None, branch_settings=settings)

    productos = await stock.get_productos("biz-1", scoped=scoped)

    assert len(productos) == 1
    assert productos[0]["stock_actual"] == 12.0


@pytest.mark.asyncio
async def test_get_productos_branch_inventory_uses_branch_stock_and_catalog() -> None:
    tables = {
        "productos": DummyTable(
            [
                {
                    "id": "prod-2",
                    "negocio_id": "biz-2",
                    "nombre": "Prod Sucursal",
                    "activo": True,
                    "precio_venta": 100,
                    "stock_minimo": 0,
                },
            ]
        ),
        "inventario_negocio": DummyTable([]),
        "inventario_sucursal": DummyTable(
            [
                {"producto_id": "prod-2", "sucursal_id": "branch-1", "stock_actual": 5},
            ]
        ),
        "producto_sucursal": DummyTable(
            [
                {
                    "producto_id": "prod-2",
                    "sucursal_id": "branch-1",
                    "precio": 120,
                    "stock_minimo": 3,
                    "estado": "activo",
                }
            ]
        ),
    }
    client = DummyScopedClient(tables)
    settings = {
        "inventario_modo": "por_sucursal",
        "catalogo_producto_modo": "por_sucursal",
        "default_branch_id": "branch-1",
    }
    scoped = DummyScopedContext(client, business_id="biz-2", branch_id="branch-1", branch_settings=settings)

    productos = await stock.get_productos("biz-2", scoped=scoped)

    assert len(productos) == 1
    producto = productos[0]
    assert producto["stock_actual"] == 5.0
    assert producto["precio_venta"] == 120.0
    assert producto["stock_minimo"] == 3.0
