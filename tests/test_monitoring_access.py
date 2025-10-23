from fastapi import FastAPI
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.api_v1.endpoints import monitoring


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_monitoring_summary_requires_tenant_access(monkeypatch, anyio_backend):
    app = FastAPI()
    app.include_router(monitoring.router, prefix="/monitoring")

    app.dependency_overrides[monitoring.get_current_user] = lambda: {"id": "user-123"}
    app.dependency_overrides[monitoring.get_supabase_client] = lambda: object()

    monkeypatch.setattr(monitoring, "_verify_tenant_access", lambda *_: False)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/monitoring/performance/tenant-abc/summary")

    assert response.status_code == 403
    assert response.json()["detail"] == "Access denied to tenant"
