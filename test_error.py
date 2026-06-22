from app.core.config import settings
from supabase import create_client

client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY)

try:
    res = client.table("venta_detalle").insert({
        "venta_id": "c36fdf48-2413-4382-b3f4-3016b088e8ab", 
        "producto_id": "0d988095-5a1f-4a88-b97a-34c4fededd5d", 
        "cantidad": 0.9, 
        "precio_unitario": 100, 
        "subtotal": 90,
        "sucursal_id": "91496986-51fd-40b7-83ba-5ade36a55044", 
        "negocio_id": "de138c82-abaa-4f3b-86de-1c98edbef33b"
    }).execute()
    print("Insert success:", res.data)
except Exception as e:
    print("Error insert:", str(e))
