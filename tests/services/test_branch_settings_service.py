from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import UUID

import pytest

from app.schemas.branch_settings import BranchSettingsUpdate
from app.services.branch_settings_service import BranchSettingsService


class MockResponse:
    def __init__(self, data: Optional[Iterable[Dict[str, Any]]]) -> None:
        self.data = list(data) if data is not None else None


class MockTable:
    def __init__(self, name: str, rows: Iterable[Dict[str, Any]] | None = None) -> None:
        self.name = name
        self.rows: List[Dict[str, Any]] = [dict(row) for row in rows or []]
        self._reset()

    # Query builder ---------------------------------------------------------
    def select(self, _columns: str = "*") -> "MockTable":
        self._mode = "select"
        self._filters: List[Tuple[str, Any]] = []
        self._limit: Optional[int] = None
        return self

    def eq(self, column: str, value: Any) -> "MockTable":
        if self._mode in {"select", "update"}:
            self._filters.append((column, value))
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

    # Execution -------------------------------------------------------------
    def execute(self) -> MockResponse:
        try:
            if self._mode == "select":
                rows = [row for row in self.rows if self._match(row)]
                if self._limit is not None:
                    rows = rows[: self._limit]
                return MockResponse([dict(row) for row in rows])

            if self._mode == "insert":
                payloads = self._as_list(self._pending)
                inserted: List[Dict[str, Any]] = []
                for payload in payloads:
                    if self.name == "negocio_configuracion" and any(
                        self._match_on_primary(existing, payload) for existing in self.rows
                    ):
                        continue  # Mimic ON CONFLICT DO NOTHING

                    entry = dict(payload)
                    now = datetime.now(timezone.utc)
                    entry.setdefault("created_at", now)
                    entry.setdefault("updated_at", now)
                    self.rows.append(entry)
                    inserted.append(dict(entry))
                return MockResponse(inserted)

            if self._mode == "update":
                updated: List[Dict[str, Any]] = []
                for row in self.rows:
                    if self._match(row):
                        row.update(self._pending)
                        updated.append(dict(row))
                return MockResponse(updated)

            return MockResponse([])
        finally:
            self._reset()

    # Helpers ---------------------------------------------------------------
    def _reset(self) -> None:
        self._mode: Optional[str] = None
        self._filters: List[Tuple[str, Any]] = []
        self._limit: Optional[int] = None
        self._pending: Any = None

    def _match(self, row: Dict[str, Any]) -> bool:
        return all(str(row.get(column)) == str(value) for column, value in self._filters)

    @staticmethod
    def _match_on_primary(existing: Dict[str, Any], payload: Dict[str, Any]) -> bool:
        if "negocio_id" in payload:
            return str(existing.get("negocio_id")) == str(payload["negocio_id"])
        return False

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
def business_id() -> str:
    return "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def table(business_id: str) -> MockTable:
    return MockTable(
        "negocio_configuracion",
        [
            {
                "negocio_id": business_id,
                "inventario_modo": "por_sucursal",
                "servicios_modo": "por_sucursal",
                "catalogo_producto_modo": "por_sucursal",
                "permite_transferencias": True,
                "transferencia_auto_confirma": False,
                "default_branch_id": None,
                "metadata": {},
                "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
                "updated_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
            }
        ],
    )


def _build_service(table: MockTable, business_id: str) -> BranchSettingsService:
    client = MockScopedClient({"negocio_configuracion": table})
    return BranchSettingsService(client, business_id)


def test_fetch_returns_existing_configuration(table: MockTable, business_id: str) -> None:
    service = _build_service(table, business_id)

    result = service.fetch(ensure_exists=True)

    assert result is not None
    assert result.negocio_id == UUID(business_id)
    assert result.inventario_modo == "por_sucursal"
    assert result.metadata == {}


def test_fetch_creates_default_when_missing(business_id: str) -> None:
    table = MockTable("negocio_configuracion")
    service = _build_service(table, business_id)

    result = service.fetch(ensure_exists=True)

    assert result is not None
    assert len(table.rows) == 1
    stored = table.rows[0]
    assert stored["negocio_id"] == business_id
    assert stored["inventario_modo"] == "por_sucursal"
    assert stored["catalogo_producto_modo"] == "por_sucursal"


def test_update_applies_changes_and_refreshes_timestamp(table: MockTable, business_id: str) -> None:
    service = _build_service(table, business_id)
    previous_updated_at = table.rows[0]["updated_at"]
    payload = BranchSettingsUpdate(
        inventario_modo="centralizado",
        default_branch_id=UUID("00000000-0000-0000-0000-000000000010"),
        metadata={"source": "test"},
    )

    result = service.update(payload)

    assert result.inventario_modo == "centralizado"
    assert result.metadata["source"] == "test"
    assert result.metadata["inventory_mode_previous"] == "por_sucursal"
    assert "inventory_mode_changed_at" in result.metadata
    assert result.metadata["inventory_mode_sync_required"] is True
    stored = table.rows[0]
    assert stored["inventario_modo"] == "centralizado"
    assert stored["metadata"]["source"] == "test"
    assert stored["metadata"]["inventory_mode_previous"] == "por_sucursal"
    assert "inventory_mode_changed_at" in stored["metadata"]
    parsed_updated_at = datetime.fromisoformat(str(stored["updated_at"]))
    assert parsed_updated_at > previous_updated_at


def test_update_with_empty_payload_returns_current(table: MockTable, business_id: str) -> None:
    service = _build_service(table, business_id)
    payload = BranchSettingsUpdate()

    result = service.update(payload)

    assert result.inventario_modo == "por_sucursal"
    assert result.metadata == {}
