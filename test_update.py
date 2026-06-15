import asyncio
import sys
sys.path.append('c:\\Users\\Usuario\\Documents\\Workspace\\micro_pymes\\backend')
from app.db.supabase_client import get_supabase_service_client

async def test_update():
    client = get_supabase_service_client()
    negocio_id = "232becca-8d7c-44d5-917d-e941e968df96"
    key_filename = f"{negocio_id}/clave_privada.key"
    
    # Check if exists
    files = client.storage.from_("certificados_afip").list(negocio_id)
    print("Files:", files)
    
    # Use update
    try:
        res = client.storage.from_("certificados_afip").update(
            file=b"test data update", 
            path=key_filename, 
            file_options={"upsert": "true", "content-type": "application/pkcs8"}
        )
        print("Update response:", res)
    except Exception as e:
        print("Update error:", e)

    # Use upload with upsert=True (bool vs string)
    try:
        res = client.storage.from_("certificados_afip").upload(
            file=b"test data upload", 
            path=key_filename, 
            file_options={"upsert": True, "content-type": "application/pkcs8"}
        )
        print("Upload response:", res)
    except Exception as e:
        print("Upload error:", e)

if __name__ == '__main__':
    asyncio.run(test_update())
