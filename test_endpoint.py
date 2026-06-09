import sys
import os
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

# Set up paths
backend_dir = r"c:\Users\Usuario\Documents\Workspace\micro_pymes\backend"
sys.path.insert(0, backend_dir)
env_path = os.path.join(backend_dir, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)

from main import app
from app.api.context import BusinessScopedClientDep, ScopedClientContext, BusinessBranchContext
from app.db.supabase_client import get_supabase_service_client

# We want to test GET /api/v1/businesses/de138c82-abaa-4f3b-86de-1c98edbef33b/branch-settings
business_id = "de138c82-abaa-4f3b-86de-1c98edbef33b"

async def mock_dep():
    # Return a mocked ScopedClientContext
    class MockClient:
        pass
    
    context = BusinessBranchContext(
        user_id="mocked_user",
        business_id=business_id,
        branch_id=None,
        usuario_negocio_id="mocked_un_id",
        user_role="admin"
    )
    return ScopedClientContext(client=MockClient(), context=context)

# Override the dependency
app.dependency_overrides[BusinessScopedClientDep] = mock_dep

client = TestClient(app)

print("Sending GET request...")
response = client.get(f"/api/v1/businesses/{business_id}/branch-settings")
print(f"Status Code: {response.status_code}")
print(f"Response JSON: {response.text}")
