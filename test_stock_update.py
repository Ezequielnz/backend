import asyncio
from app.db.supabase_client import get_supabase_service_client
import sys

def main():
    svc = get_supabase_service_client()
    try:
        # Reemplazar con UUIDs reales.
        business_id = 'e94c911f-2003-4f92-a532-c23f126a8593'
        branch_id = 'd08371cf-a0c4-42cf-be87-15f15bf5f2b6'
        producto_id = '4ade70b4-f51c-4f1b-bec5-e023018e7a99'
        
        # Simular update por_sucursal
        inv_resp2 = (
            svc
            .table("inventario_sucursal")
            .select("id, stock_actual")
            .eq("producto_id", producto_id)
            .eq("sucursal_id", branch_id)
            .eq("negocio_id", business_id)
            .execute()
        )
        print("inv_resp2:", inv_resp2.data)
        actual = inv_resp2.data[0].get("stock_actual", 0) if inv_resp2.data else 0
        nuevo = int(actual) + 5
        
        if inv_resp2.data:
            upd = svc.table("inventario_sucursal").update({
                "stock_actual": nuevo
            }).eq("id", inv_resp2.data[0]["id"]).execute()
            print("update inv:", upd.data)
        
        upd2 = svc.table("productos").update({
            "precio_compra": 15.5
        }).eq("id", producto_id).execute()
        print("update prod:", upd2.data)
        
    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    main()
