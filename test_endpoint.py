import asyncio
from app.db.supabase_client import get_supabase_service_client

async def test_get_productos():
    from app.api.api_v1.endpoints.stock import get_productos
    from app.schemas import types
    from fastapi import Request
    from unittest.mock import Mock
    from app.db.scoped_client import ScopedClientContext
    
    # This is a bit tricky to mock out perfectly due to ScopedClientContext,
    # let's just do a direct manual call inside FastAPI test client or just using httpx if the server is running.
    
    pass

import httpx
async def test_endpoint_http():
    # If the user has a local server running on port 8000
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/api/v1/stock/?business_id=de138c82-abaa-4f3b-86de-1c98edbef33b")
            if resp.status_code == 200:
                data = resp.json()
                if data and len(data) > 0:
                    print("First product keys:", data[0].keys())
                    print("stock_por_sucursal for first product:", data[0].get("stock_por_sucursal"))
            else:
                print("Status code:", resp.status_code, resp.text)
    except Exception as e:
        print("Could not connect to localhost:8000", str(e))

if __name__ == "__main__":
    asyncio.run(test_endpoint_http())
