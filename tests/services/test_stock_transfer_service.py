from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Tuple
from uuid import UUID, uuid4

import pytest

from app.schemas.stock_transfer import StockTransferCreate, StockTransferItemCreate
from app.services import stock_transfer_service as sts_module
from app.services.stock_transfer_service import (
    StockTransferNotAllowedError,
    StockTransferService,
    StockTransferValidationError,
)


class MockResponse:
    def __init__(self, data: Iterable[Dict[str, Any]] | None) -> None:
        self.data = list(data) if data is not None else None


class MockTable:
    def __init__(self, name: str, rows: Iterable[Dict[str, Any]]) -> None:
        self.name = name
        self.rows: List[Dict[str, Any]] = [dict(row) for row in rows]
        self._reset()

    # Query building methods -------------------------------------------------
    def select(self, _columns: str = "*") -> "MockTable":
        self._mode = "select"
        self._filters = []
        self._limit = None
        self._order = []
        self._in_filters = []
        return self

    def eq(self, column: str, value: Any) -> "MockTable":
        if self._mode in {"select", "update", "delete"}:
            self._filters.append((column, value))
        return self

    def in_(self, column: str, values: Iterable[Any]) -> "MockTable":
        if self._mode in {"select", "delete"}:
            self._in_filters.append((column, {str(value) for value in values}))
        return self

    def order(self, column: str, *, desc: bool = False) -> "MockTable":
        if self._mode == "select":
            self._order.append((column, desc))
        return self

    def limit(self, value: int) -> "MockTable":
        self._limit = value
        return self

    def insert(self, data: Dict[str, Any] | List[Dict[str, Any]]) -> "MockTable":
        self._mode = "insert"
        self._pending = data
        return self

    def update(self, data: Dict[str, Any]) -> "MockTable":
        self._mode = "update"
        self._pending = data
        return self

    def delete(self) -> "MockTable":
        self._mode = "delete"
        return self

    # Execution --------------------------------------------------------------
    def execute(self) -> MockResponse:
        try:
            if self._mode == "select":
                rows = [row for row in self.rows if self._match(row)]
                if self._order:
                    for column, desc in reversed(self._order):
                        rows.sort(
                            key=lambda row: self._order_key(row, column),
                            reverse=desc,
                        )
                if self._limit is not None:
                    rows = rows[: self._limit]
                return MockResponse([row.copy() for row in rows])
            if self._mode == "insert":
                inserted = []
                for row in self._as_list(self._pending):
                    entry = dict(row)
                    entry.setdefault("id", str(uuid4()))
                    now = datetime.now(timezone.utc)
                    entry.setdefault("created_at", now)
                    entry.setdefault("updated_at", now)
                    self.rows.append(entry)
                    inserted.append(dict(entry))
                return MockResponse(inserted)
            if self._mode == "update":
                updated = []
                for row in self.rows:
                    if self._match(row):
                        row.update(self._pending)
                        updated.append(dict(row))
                return MockResponse(updated)
            if self._mode == "delete":
                before = len(self.rows)
                self.rows = [row for row in self.rows if not self._match(row)]
                return MockResponse([{"deleted": before - len(self.rows)}])
            return MockResponse([])
        finally:
            self._reset()

    # Helpers ----------------------------------------------------------------
    def _reset(self) -> None:
        self._mode: str | None = None
        self._filters: List[Tuple[str, Any]] = []
        self._limit: int | None = None
        self._pending: Any = None
        self._order: List[Tuple[str, bool]] = []
        self._in_filters: List[Tuple[str, set[str]]] = []

    def _match(self, row: Dict[str, Any]) -> bool:
        for column, value in self._filters:
            if str(row.get(column)) != str(value):
                return False
        for column, values in self._in_filters:
            if str(row.get(column)) not in values:
                return False
        return True

    @staticmethod
    def _order_key(row: Dict[str, Any], column: str) -> Any:
        value = row.get(column)
        if isinstance(value, datetime):
            return value
        if value is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def _as_list(data: Dict[str, Any] | List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if isinstance(data, list):
            return data
        return [data]


class MockScopedClient:
    def __init__(self, tables: Dict[str, MockTable]) -> None:
        self._tables = tables

    def table(self, name: str) -> MockTable:
        return self._tables[name]


@pytest.fixture
def dummy_event(monkeypatch: pytest.MonkeyPatch) -> List[Tuple[str, Dict[str, Any]]]:
    events: List[Tuple[str, Dict[str, Any]]] = []

    class Producer:
        def delay(self, event_type: str, payload: Dict[str, Any]) -> None:
            events.append((event_type, payload))

    monkeypatch.setattr(sts_module, "notify_stock_transfer_event", Producer())
    return events


def _build_service(
    *,
    dummy_event: List[Tuple[str, Dict[str, Any]]],
    inventory_mode: str = "por_sucursal",
    permite_transferencias: bool = True,
    auto_confirm: bool = False,
    origin_stock: str = "10",
    dest_stock: str = "2",
) -> Tuple[StockTransferService, Dict[str, MockTable], UUID, UUID, UUID, str]:
    business_id = UUID("00000000-0000-0000-0000-000000000001")
    origin_branch = UUID("00000000-0000-0000-0000-000000000010")
    dest_branch = UUID("00000000-0000-0000-0000-000000000011")
    product_id = UUID("00000000-0000-0000-0000-000000000100")
    user_id = "00000000-0000-0000-0000-000000000200"

    tables = {
        "sucursales": MockTable(
            "sucursales",
            [
                {"id": str(origin_branch), "negocio_id": str(business_id)},
                {"id": str(dest_branch), "negocio_id": str(business_id)},
            ],
        ),
        "productos": MockTable(
            "productos",
            [
                {"id": str(product_id), "negocio_id": str(business_id)},
            ],
        ),
        "inventario_sucursal": MockTable(
            "inventario_sucursal",
            [
                {
                    "id": "inv-origin",
                    "negocio_id": str(business_id),
                    "sucursal_id": str(origin_branch),
                    "producto_id": str(product_id),
                    "stock_actual": origin_stock,
                },
                {
                    "id": "inv-dest",
                    "negocio_id": str(business_id),
                    "sucursal_id": str(dest_branch),
                    "producto_id": str(product_id),
                    "stock_actual": dest_stock,
                },
            ],
        ),
        "inventario_negocio": MockTable(
            "inventario_negocio",
            [
                {
                    "id": "inv-business",
                    "negocio_id": str(business_id),
                    "producto_id": str(product_id),
                    "stock_total": str(
                        Decimal(origin_stock or "0") + Decimal(dest_stock or "0")
                    ),
                }
            ],
        ),
        "stock_transferencias": MockTable("stock_transferencias", []),
        "stock_transferencias_detalle": MockTable("stock_transferencias_detalle", []),
    }

    client = MockScopedClient(tables)
    settings = {
        "negocio_id": business_id,
        "inventario_modo": inventory_mode,
        "servicios_modo": "por_sucursal",
        "catalogo_producto_modo": "por_sucursal",
        "permite_transferencias": permite_transferencias,
        "transferencia_auto_confirma": auto_confirm,
        "default_branch_id": None,
        "metadata": {},
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    service = StockTransferService(client, str(business_id), user_id, settings)
    return service, tables, origin_branch, dest_branch, product_id, str(business_id)


def _make_payload(origin_branch: UUID, dest_branch: UUID, product_id: UUID, qty: str = "3") -> StockTransferCreate:
    return StockTransferCreate(
        origen_sucursal_id=origin_branch,
        destino_sucursal_id=dest_branch,
        comentarios="Envio de prueba",
        items=[
            StockTransferItemCreate(
                producto_id=product_id,
                cantidad=Decimal(qty),
            )
        ],
    )


def _get_stock(tables: Dict[str, MockTable], branch_id: UUID, product_id: UUID) -> Decimal:
    table = tables["inventario_sucursal"]
    for row in table.rows:
        if row["sucursal_id"] == str(branch_id) and row["producto_id"] == str(product_id):
            return Decimal(str(row.get("stock_actual", "0")))
    return Decimal("0")


def test_create_transfer_registers_header_and_details(dummy_event: List[Tuple[str, Dict[str, Any]]]) -> None:
    service, tables, origin, dest, product_id, _ = _build_service(dummy_event=dummy_event)
    payload = _make_payload(origin, dest, product_id)

    transfer = service.create_transfer(payload)

    assert transfer.estado == "borrador"
    assert len(transfer.items) == 1
    assert len(tables["stock_transferencias"].rows) == 1
    assert len(tables["stock_transferencias_detalle"].rows) == 1
    assert dummy_event[0][0] == "created"


def test_confirm_transfer_updates_origin_inventory(dummy_event: List[Tuple[str, Dict[str, Any]]]) -> None:
    service, tables, origin, dest, product_id, _ = _build_service(dummy_event=dummy_event)
    payload = _make_payload(origin, dest, product_id, qty="4")
    transfer = service.create_transfer(payload)

    confirmed = service.confirm_transfer(transfer.id)

    assert confirmed.estado == "confirmada"
    assert _get_stock(tables, origin, product_id) == Decimal("6")
    assert [event for event, _ in dummy_event] == ["created", "confirmed"]


def test_receive_transfer_updates_destination_inventory(dummy_event: List[Tuple[str, Dict[str, Any]]]) -> None:
    service, tables, origin, dest, product_id, _ = _build_service(dummy_event=dummy_event)
    payload = _make_payload(origin, dest, product_id, qty="2")
    transfer = service.create_transfer(payload)
    service.confirm_transfer(transfer.id)

    received = service.receive_transfer(transfer.id)

    assert received.estado == "recibida"
    assert _get_stock(tables, dest, product_id) == Decimal("4")
    assert [event for event, _ in dummy_event] == ["created", "confirmed", "received"]


def test_delete_transfer_removes_records(dummy_event: List[Tuple[str, Dict[str, Any]]]) -> None:
    service, tables, origin, dest, product_id, _ = _build_service(dummy_event=dummy_event)
    payload = _make_payload(origin, dest, product_id)
    transfer = service.create_transfer(payload)

    service.delete_transfer(transfer.id)

    assert tables["stock_transferencias"].rows == []
    assert [event for event, _ in dummy_event] == ["created", "deleted"]


def test_confirm_transfer_insufficient_stock_raises(dummy_event: List[Tuple[str, Dict[str, Any]]]) -> None:
    service, tables, origin, dest, product_id, _ = _build_service(
        dummy_event=dummy_event,
        origin_stock="1",
    )
    payload = _make_payload(origin, dest, product_id, qty="5")
    transfer = service.create_transfer(payload)

    with pytest.raises(StockTransferValidationError):
        service.confirm_transfer(transfer.id)

    assert _get_stock(tables, origin, product_id) == Decimal("1")
    assert [event for event, _ in dummy_event] == ["created"]


def test_create_transfer_not_allowed(dummy_event: List[Tuple[str, Dict[str, Any]]]) -> None:
    service, _, origin, dest, product_id, _ = _build_service(
        dummy_event=dummy_event,
        permite_transferencias=False,
    )
    payload = _make_payload(origin, dest, product_id)

    with pytest.raises(StockTransferNotAllowedError):
        service.create_transfer(payload)

    assert dummy_event == []


def test_auto_confirm_transfer(dummy_event: List[Tuple[str, Dict[str, Any]]]) -> None:
    service, tables, origin, dest, product_id, _ = _build_service(
        dummy_event=dummy_event,
        auto_confirm=True,
    )
    payload = _make_payload(origin, dest, product_id, qty="3")

    transfer = service.create_transfer(payload)

    assert transfer.estado == "confirmada"
    assert _get_stock(tables, origin, product_id) == Decimal("7")
    assert [event for event, _ in dummy_event] == ["created", "confirmed"]


def test_centralized_inventory_skips_branch_adjustments(dummy_event: List[Tuple[str, Dict[str, Any]]]) -> None:
    service, tables, origin, dest, product_id, _ = _build_service(
        dummy_event=dummy_event,
        inventory_mode="centralizado",
    )
    payload = _make_payload(origin, dest, product_id, qty="3")
    transfer = service.create_transfer(payload)

    service.confirm_transfer(transfer.id)
    service.receive_transfer(transfer.id)

    # Inventario por sucursal no se altera en modo centralizado
    assert _get_stock(tables, origin, product_id) == Decimal("10")
    assert _get_stock(tables, dest, product_id) == Decimal("2")
    assert [event for event, _ in dummy_event] == ["created", "confirmed", "received"]


def test_list_transfers_filters_by_status(dummy_event: List[Tuple[str, Dict[str, Any]]]) -> None:
    service, _, origin, dest, product_id, _ = _build_service(dummy_event=dummy_event)

    first_transfer = service.create_transfer(_make_payload(origin, dest, product_id, qty="2"))
    service.confirm_transfer(first_transfer.id)

    second_transfer = service.create_transfer(_make_payload(origin, dest, product_id, qty="1"))

    all_transfers = service.list_transfers()
    assert len(all_transfers) == 2
    assert {transfer.id for transfer in all_transfers} == {first_transfer.id, second_transfer.id}

    confirmed_only = service.list_transfers(estado="confirmada")
    assert len(confirmed_only) == 1
    assert confirmed_only[0].id == first_transfer.id
    assert confirmed_only[0].estado == "confirmada"
