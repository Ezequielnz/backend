import asyncio
import sys
sys.path.append('c:\\Users\\Usuario\\Documents\\Workspace\\micro_pymes\\backend')
from app.db.supabase_client import get_supabase_service_client

async def test_upsert():
    client = get_supabase_service_client()
    business_id = "232becca-8d7c-44d5-917d-e941e968df96"
    
    # 1. Fetch current
    res = client.table("configuracion_fiscal").select("*").eq("negocio_id", business_id).execute()
    print("Current data:", res.data)
    
    if not res.data:
        print("No data found")
        return
        
    config_data = res.data[0]
    config_data["cert_path"] = f"{business_id}/certificado.crt"
    
    print("Upserting:", config_data)
    try:
        upsert_res = client.table("configuracion_fiscal").upsert(
            config_data, 
            on_conflict="negocio_id"
        ).execute()
        print("Upsert success:", upsert_res.data)
    except Exception as e:
        print("Upsert error:", repr(e))

if __name__ == '__main__':
    asyncio.run(test_upsert())
