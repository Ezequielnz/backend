import sys
import os
from dotenv import load_dotenv

# Set up paths
backend_dir = r"c:\Users\Usuario\Documents\Workspace\micro_pymes\backend"
sys.path.insert(0, backend_dir)

# Load env vars manually if .env exists
env_path = os.path.join(backend_dir, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)

from app.services.branch_settings_service import BranchSettingsService

business_id = "de138c82-abaa-4f3b-86de-1c98edbef33b"

class MockScopedClient:
    pass

print("Testing BranchSettingsService.fetch()...")
try:
    svc = BranchSettingsService(MockScopedClient(), business_id)
    res = svc.fetch(ensure_exists=True)
    print("Fetch succeeded!")
    print(res)
except Exception as e:
    print("Fetch failed!")
    import traceback
    traceback.print_exc()
