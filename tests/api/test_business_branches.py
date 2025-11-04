from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Tuple
from uuid import UUID

import pytest
from starlette.requests import Request

from app.api.api_v1.endpoints import businesses
from app.schemas.branch import BranchCreate, BranchUpdate


class MockResponse:
    def __init__(self, data: List[Dict[str, Any]] | None) -> None:
        self.data = data


class MockQuery:
    def __init__(self, name: str, client: "MockSupabaseClient") -> None:
        self.name = name
        self.client = client
        self._mode: str | None = None
        self._payload: Any = None
        self._filters: List[Tuple[str, Any]] = []

    def select(self, *_args: Any, **_kwargs: Any) -> "MockQuery":
        self._mode = "select"
        return self

    def eq(self, column: str, value: Any) -> "MockQuery":
        self._filters.append((column, value))
        return self

    def limit(self, _value: int) -> "MockQuery":
        return self

    def insert(self, payload: Any) -> "MockQuery":
        self._mode = "insert"
        self._payload = payload
        return self

    def update(self, payload: Dict[str, Any]) -> "MockQuery":
        self._mode = "update"
        self._payload = payload
        return self

    def execute(self) -> MockResponse:
        if self.name == "usuarios_negocios" and self._mode == "select":
            return MockResponse([{"rol": self.client.membership_role}])

        if self.name == "sucursales" and self._mode == "insert":
            payload = dict(self._payload)
            if isinstance(payload, list):
                payload = payload[0]
            branch = {
                "id": payload["id"],
                "negocio_id": payload["negocio_id"],
                "nombre": payload.get("nombre"),
                "codigo": payload.get("codigo"),
                "direccion": payload.get("direccion"),
                "activo": payload.get("activo", True),
                "is_main": payload.get("is_main", False),
                "creado_en": "2025-01-01T00:00:00Z",
                "actualizado_en": "2025-01-01T00:00:00Z",
            }
            self.client.created_branches.append(branch)
            return MockResponse([branch])

        if self.name == "usuarios_sucursales" and self._mode == "select":
            return MockResponse(self.client.assignments)

        if self.name == "usuarios_sucursales" and self._mode == "insert":
            payload = dict(self._payload)
            self.client.assignments.append(payload)
            return MockResponse([payload])

        if self.name == "sucursales" and self._mode == "update":
            branch_id = next((value for column, value in self._filters if column == "id"), "branch-id")
            updated = {
                "id": branch_id,
                "negocio_id": self.client.business_id,
                "nombre": self._payload.get("nombre", "Sucursal Norte"),
                "codigo": self._payload.get("codigo", "COD"),
                "direccion": self._payload.get("direccion", "Dirección"),
                "activo": self._payload.get("activo", True),
                "is_main": self._payload.get("is_main", False),
                "creado_en": "2025-01-01T00:00:00Z",
                "actualizado_en": "2025-01-02T00:00:00Z",
            }
            self.client.updated_branches.append(updated)
            return MockResponse([updated])

        if self.name == "sucursales" and self._mode == "select":
            branch_id = next((value for column, value in self._filters if column == "id"), "branch-id")
            return MockResponse(
                [
                    {
                        "id": branch_id,
                        "negocio_id": self.client.business_id,
                        "nombre": "Sucursal Norte",
                        "codigo": "NOR",
                        "direccion": "Av. Siempre Viva",
                        "activo": True,
                        "is_main": False,
                        "creado_en": "2025-01-01T00:00:00Z",
                        "actualizado_en": "2025-01-01T00:00:00Z",
                    }
                ]
            )

        return MockResponse([])


class MockSupabaseClient:
    def __init__(self, business_id: str, membership_role: str = "owner") -> None:
        self.business_id = business_id
        self.membership_role = membership_role
        self.created_branches: List[Dict[str, Any]] = []
        self.updated_branches: List[Dict[str, Any]] = []
        self.assignments: List[Dict[str, Any]] = []

    def table(self, name: str) -> MockQuery:
        return MockQuery(name, self)


def _build_request(user_id: str = "user-1") -> Request:
    scope = {"type": "http", "headers": []}
    request = Request(scope=scope)
    request.state.user = SimpleNamespace(id=user_id)
    return request


@pytest.mark.asyncio
async def test_create_branch_inserts_record(monkeypatch: pytest.MonkeyPatch) -> None:
    business_id = "00000000-0000-0000-0000-000000000010"
    mock_client = MockSupabaseClient(business_id)
    branch_uuid = UUID("00000000-0000-0000-0000-000000000099")

    monkeypatch.setattr(businesses, "get_supabase_user_client", lambda _token: mock_client)
    monkeypatch.setattr(businesses, "get_supabase_service_client", lambda: mock_client)
    monkeypatch.setattr(businesses, "uuid4", lambda: branch_uuid)

    request = _build_request()
    payload = BranchCreate(nombre="Sucursal Centro", codigo="CTR", direccion="Calle Falsa 123", is_main=False)

    result = await businesses.create_business_branch(business_id, payload, request)

    assert result.id == branch_uuid
    assert result.nombre == "Sucursal Centro"
    assert len(mock_client.created_branches) == 1
    assert mock_client.assignments[0]["usuario_id"] == "user-1"


@pytest.mark.asyncio
async def test_update_branch_returns_updated_row(monkeypatch: pytest.MonkeyPatch) -> None:
    business_id = "00000000-0000-0000-0000-000000000010"
    mock_client = MockSupabaseClient(business_id)

    monkeypatch.setattr(businesses, "get_supabase_user_client", lambda _token: mock_client)
    monkeypatch.setattr(businesses, "get_supabase_service_client", lambda: mock_client)

    request = _build_request()
    branch_id = UUID("00000000-0000-0000-0000-000000000120")
    payload = BranchUpdate(nombre="Sucursal Renombrada", activo=False)

    result = await businesses.update_business_branch(business_id, branch_id, payload, request)

    assert result.id == branch_id
    assert result.nombre == "Sucursal Renombrada"
    assert result.activo is False
    assert len(mock_client.updated_branches) == 1
