import asyncio
from app.db.supabase_client import get_supabase_service_client

async def check_settings():
    client = get_supabase_service_client()
    b_resp = client.table("negocios").select("id").limit(1).execute()
    bid = b_resp.data[0]["id"]
    
    c_resp = client.table("negocio_configuracion").select("default_branch_id").eq("negocio_id", bid).execute()
    print("Configuracion:", c_resp.data)

if __name__ == "__main__":
    asyncio.run(check_settings())
