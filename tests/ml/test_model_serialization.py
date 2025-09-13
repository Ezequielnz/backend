import types
import base64
import pytest
from typing import Any, cast

from app.services.ml.model_version_manager import ModelVersionManager


class FakeQuery:
    def __init__(self, table_name: str, store: dict[str, list[dict[str, Any]]]):
        self.table_name = table_name
        self._store = store
        self._select: str | None = None
        self._filters: list[tuple[str, str, Any]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._payload: dict[str, Any] | list[dict[str, Any]] | None = None
        self._on_conflict: str | None = None

    def select(self, fields: str) -> "FakeQuery":
        self._select = fields
        return self

    def eq(self, field: str, value: Any) -> "FakeQuery":
        self._filters.append(("eq", field, value))
        return self

    def order(self, field: str, desc: bool = False) -> "FakeQuery":
        self._order = (field, desc)
        return self

    def limit(self, n: int) -> "FakeQuery":
        self._limit = n
        return self

    def upsert(self, payload: Any, on_conflict: str | None = None) -> "FakeQuery":
        self._payload = cast(dict[str, Any], payload)
        self._on_conflict = on_conflict
        return self

    def execute(self) -> Any:
        if self.table_name == "ml_models" and self._payload is not None:
            row = cast(dict[str, Any], self._payload).copy()
            # Simulate DB-generated fields
            row.setdefault("id", f"model_{len(self._store.setdefault('ml_models', [])) + 1}")
            row.setdefault("created_at", "2024-01-01T00:00:00Z")
            # Apply on_conflict upsert semantics on (tenant_id, model_type, model_version)
            keys = [k.strip() for k in (self._on_conflict or "").split(",") if k.strip()]
            existing = self._store.setdefault("ml_models", [])
            if keys:
                def _match(e: dict[str, Any]) -> bool:
                    return all(str(e.get(k)) == str(row.get(k)) for k in keys)
                idx = next((i for i, e in enumerate(existing) if _match(e)), None)
                if idx is None:
                    existing.append(row)
                else:
                    existing[idx] = row
            else:
                existing.append(row)
            return types.SimpleNamespace(data=[row])
        if self.table_name == "ml_models" and self._select:
            # Build filtered result
            rows = list(self._store.get("ml_models", []))
            for op, field, value in self._filters:
                if op == "eq":
                    rows = [r for r in rows if r.get(field) == value]
            # Sort by last_trained desc if requested
            if self._order and self._order[0] == "last_trained":
                rows.sort(key=lambda r: r.get("last_trained", ""), reverse=bool(self._order[1]))
            if self._limit:
                rows = rows[: self._limit]
            # Only return selected fields
            if self._select:
                select_fields = [f.strip() for f in self._select.split(",")]
                rows = [{k: v for k, v in r.items() if k in select_fields} for r in rows]
            return types.SimpleNamespace(data=rows)
        return types.SimpleNamespace(data=[])


class FakeSupabase:
    def __init__(self) -> None:
        self.store: dict[str, list[dict[str, Any]]] = {}

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(name, self.store)


def test_model_serialization_and_load_active(monkeypatch: pytest.MonkeyPatch):
    fake = FakeSupabase()
    # Patch client used inside ModelVersionManager
    from app.services.ml import model_version_manager as mvm_mod
    monkeypatch.setattr(mvm_mod, "get_supabase_service_client", lambda: fake)

    mvm = ModelVersionManager()
    model_obj = {"type": "baseline", "variant": "naive", "season": 7}

    saved = mvm.save_model(
        tenant_id="t1",
        model_type="sales_forecasting",
        model=model_obj,
        model_version="1.0",
        hyperparameters={"foo": 1},
        training_metrics={"bar": 2},
        accuracy=0.9,
        is_active=True,
    )

    assert saved.id and saved.tenant_id == "t1"

    # Ensure the stored model_data looks like base64
    rows = fake.store.get("ml_models", [])
    assert rows, "No model rows persisted"
    blob = rows[0].get("model_data")
    assert isinstance(blob, str)
    # Should be decodable base64
    base64.b64decode(blob)

    # Now load active model
    loaded = mvm.load_active_model("t1", "sales_forecasting")
    assert isinstance(loaded, dict)
    assert loaded == model_obj
