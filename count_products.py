import asyncio
from app.db.supabase_client import get_supabase_service_client

async def count_products():
    client = get_supabase_service_client()
    b_resp = client.table("negocios").select("id").limit(1).execute()
    bid = b_resp.data[0]["id"]
    
    p_resp = client.table("productos").select("id, stock_actual").eq("negocio_id", bid).execute()
    print("Total products:", len(p_resp.data))
    for p in p_resp.data:
        if float(p["stock_actual"] or 0) > 0:
            print("Product has stock_actual > 0 in productos table:", p)

    i_neg = client.table("inventario_negocio").select("*").eq("negocio_id", bid).execute()
    print("Total in inventario_negocio:", len(i_neg.data))
    for i in i_neg.data:
        print("inventario_negocio:", i)
        
    i_suc = client.table("inventario_sucursal").select("*").eq("negocio_id", bid).execute()
    print("Total in inventario_sucursal:", len(i_suc.data))

if __name__ == "__main__":
    asyncio.run(count_products())
