import sys
import asyncio
from cryptography import x509
from cryptography.hazmat.backends import default_backend

sys.path.append('c:\\Users\\Usuario\\Documents\\Workspace\\micro_pymes\\backend')
from app.db.supabase_client import get_supabase_service_client

async def check_cert():
    client = get_supabase_service_client()
    negocio_id = "232becca-8d7c-44d5-917d-e941e968df96"
    
    cert_bytes = client.storage.from_("certificados_afip").download(f"{negocio_id}/certificado.crt")
    cert = x509.load_pem_x509_certificate(cert_bytes, default_backend())
    
    print("Issuer:", cert.issuer.rfc4514_string())
    print("Subject:", cert.subject.rfc4514_string())

if __name__ == '__main__':
    asyncio.run(check_cert())
