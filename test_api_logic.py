import asyncio
import sys
sys.path.append('c:\\Users\\Usuario\\Documents\\Workspace\\micro_pymes\\backend')
from app.db.supabase_client import get_supabase_service_client

async def test_api_code():
    service_client = get_supabase_service_client()
    business_id = "232becca-8d7c-44d5-917d-e941e968df96"
    cert_filename = f"{business_id}/certificado.crt"
    cert_data = b"test cert data 2"
    
    bucket = service_client.storage.from_("certificados_afip")
    
    try:
        bucket.upload(
            file=cert_data, 
            path=cert_filename, 
            file_options={"content-type": "application/x-x509-ca-cert"}
        )
        print("Upload succeeded")
    except Exception as e:
        print("Upload failed, checking fallback. Error:", repr(e))
        if "Duplicate" in str(e) or "already exists" in str(e) or "400" in str(e):
            try:
                print("Trying update...")
                getattr(bucket, "update")(
                    file=cert_data, 
                    path=cert_filename, 
                    file_options={"content-type": "application/x-x509-ca-cert"}
                )
                print("Update succeeded")
            except Exception as update_err:
                print("Update failed:", repr(update_err))
        else:
            print("Different error:", repr(e))

if __name__ == '__main__':
    asyncio.run(test_api_code())
