import asyncio
import sys
sys.path.append('c:\\Users\\Usuario\\Documents\\Workspace\\micro_pymes\\backend')
from app.db.supabase_client import get_supabase_service_client

async def check():
    client = get_supabase_service_client()
    bucket = client.storage.from_("certificados_afip")
    print(dir(bucket))

if __name__ == '__main__':
    asyncio.run(check())
