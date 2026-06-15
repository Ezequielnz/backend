import asyncio
import sys
sys.path.append('c:\\Users\\Usuario\\Documents\\Workspace\\micro_pymes\\backend')
from app.db.supabase_client import get_supabase_service_client

async def test_remove():
    client = get_supabase_service_client()
    negocio_id = "232becca-8d7c-44d5-917d-e941e968df96"
    key_filename = f"{negocio_id}/clave_privada.key"
    fake_filename = f"{negocio_id}/no_existe.crt"
    
    # Try remove with one fake and one real
    try:
        res = client.storage.from_("certificados_afip").remove([key_filename, fake_filename])
        print("Remove batch response:", res)
    except Exception as e:
        print("Error remove batch:", e)

    files = client.storage.from_("certificados_afip").list(negocio_id)
    print("Files after batch remove:", [f['name'] for f in files])

if __name__ == '__main__':
    asyncio.run(test_remove())
