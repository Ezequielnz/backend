import asyncio
from app.db.supabase_client import get_supabase_service_client

async def test_upsert():
    client = get_supabase_service_client()
    
    # Get a business and a product
    prod_resp = client.table("productos").select("id, negocio_id").limit(1).execute()
    if not prod_resp.data:
        print("No products found")
        return
    
    prod = prod_resp.data[0]
    pid = prod["id"]
    nid = prod["negocio_id"]
    
    # Get a branch
    branch_resp = client.table("sucursales").select("id").eq("negocio_id", nid).limit(1).execute()
    if not branch_resp.data:
        print("No branches found")
        return
        
    bid = branch_resp.data[0]["id"]
    
    payload = {
        "negocio_id": nid,
        "sucursal_id": bid,
        "producto_id": pid,
        "stock_actual": 99.0,
    }
    
    try:
        resp = client.table("inventario_sucursal").upsert(payload, on_conflict="sucursal_id,producto_id").execute()
        print("Upsert successful:", resp.data)
    except Exception as e:
        print("Upsert failed:", str(e))
        
if __name__ == "__main__":
    asyncio.run(test_upsert())
