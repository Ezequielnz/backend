import sys
import asyncio
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

sys.path.append('c:\\Users\\Usuario\\Documents\\Workspace\\micro_pymes\\backend')
from app.db.supabase_client import get_supabase_service_client

async def verify_match():
    client = get_supabase_service_client()
    negocio_id = "232becca-8d7c-44d5-917d-e941e968df96"
    
    try:
        cert_bytes = client.storage.from_("certificados_afip").download(f"{negocio_id}/certificado.crt")
        key_bytes = client.storage.from_("certificados_afip").download(f"{negocio_id}/clave_privada.key")
        
        cert = x509.load_pem_x509_certificate(cert_bytes, default_backend())
        cert_pub = cert.public_key().public_numbers()
        
        key = serialization.load_pem_private_key(key_bytes, password=None, backend=default_backend())
        key_pub = key.public_key().public_numbers()
        
        if cert_pub == key_pub:
            print("MATCH: El certificado y la clave privada coinciden.")
        else:
            print("MISMATCH: El certificado NO corresponde a esta clave privada.")
            
    except Exception as e:
        print("Error verificando:", e)

if __name__ == '__main__':
    asyncio.run(verify_match())
