import asyncio
from app.db.supabase_client import get_supabase_service_client

async def check_inventory():
    client = get_supabase_service_client()
    
    # 1. get a business
    b_resp = client.table("negocios").select("id").limit(1).execute()
    if not b_resp.data:
        print("No business found")
        return
    bid = b_resp.data[0]["id"]
    print("Business ID:", bid)
    
    # 2. Get branches
    s_resp = client.table("sucursales").select("id, nombre, is_main, activo").eq("negocio_id", bid).execute()
    for s in s_resp.data:
        print("Branch:", s)
        
    # 3. Get inventario_sucursal
    i_resp = client.table("inventario_sucursal").select("sucursal_id, producto_id, stock_actual").eq("negocio_id", bid).execute()
    for row in i_resp.data:
        if row["stock_actual"] > 0:
            print("Inventario > 0:", row)
            
if __name__ == "__main__":
    asyncio.run(check_inventory())
