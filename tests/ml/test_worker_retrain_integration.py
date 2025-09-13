import types
import pytest
from typing import Any, cast

from app.workers import ml_worker


class FakeQuery:
    def __init__(self, table_name: str):
        self.table_name = table_name
        self._select: str | None = None
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None
        self._order: tuple[str, bool] | None = None

    def select(self, fields: str) -> "FakeQuery":
        self._select = fields
        return self

    def eq(self, field: str, value: Any) -> "FakeQuery":
        self._filters.append(("eq", field, value))
        return self

    def limit(self, n: int) -> "FakeQuery":
        self._limit = n
        return self

    def order(self, field: str, desc: bool = False) -> "FakeQuery":
        self._order = (field, desc)
        return self

    def execute(self) -> Any:
        if self.table_name == "negocios":
            # Minimal negocios list
            return types.SimpleNamespace(data=[
                {"id": "t1", "nombre": "Negocio 1"},
                {"id": "t2", "nombre": "Negocio 2"},
            ])
        return types.SimpleNamespace(data=[])


class FakeSupabase:
    def table(self, name: str) -> FakeQuery:
        return FakeQuery(name)


def test_retrain_all_models_integration(monkeypatch: pytest.MonkeyPatch):
    # Patch Supabase service client where worker looks it up
    # Workers import get_supabase_service_client inside the function from app.db.supabase_client
    import app.db.supabase_client as sb
    monkeypatch.setattr(sb, "get_supabase_service_client", lambda: FakeSupabase())

    # Patch pipeline entrypoint imported in worker to avoid heavy training
    calls: list[str] = []

    def _fake_train_and_predict_sales(bid: str, **kwargs: Any) -> dict[str, Any]:
        calls.append(bid)
        return {
            "trained": True,
            "forecasts_inserted": 7,
            "accuracy": 0.8,
            "metrics_summary": {
                "selected_model": "naive",
                "mape": 0.2,
                "cv": {"folds": kwargs.get("cv_folds", 2)}
            }
        }

    from app.workers import ml_worker as mw
    monkeypatch.setattr(mw, "train_and_predict_sales", _fake_train_and_predict_sales)

    # Act: call the Celery task body via .run() to avoid needing a worker
    result = ml_worker.retrain_all_models.run()  # type: ignore[attr-defined]

    # Assert
    assert isinstance(result, dict)
    assert result.get("task") == "retrain_all_models"
    # Two businesses processed
    assert result.get("businesses_processed") == 2
    # We expect at least one model retrained and forecasts aggregated
    assert result.get("models_retrained") >= 1
    assert result.get("forecasts_inserted") == 14  # 2 * 7
    # Ensure our stub was called for both tenants
    assert set(calls) == {"t1", "t2"}
