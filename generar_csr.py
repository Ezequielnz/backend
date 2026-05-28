from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes

CUIT = "23283176789" # Reemplaza con tu CUIT
RAZON_SOCIAL = "Daniel Alejandro Nuñez" # Reemplaza con tu Razón Social

# 1. Generar Llave Privada (.key)
private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
with open("homologacion.key", "wb") as f:
    f.write(private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ))

# 2. Generar Pedido de Certificado (.csr)
builder = x509.CertificateSigningRequestBuilder()
builder = builder.subject_name(x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, RAZON_SOCIAL),
    x509.NameAttribute(NameOID.SERIAL_NUMBER, f"CUIT {CUIT}")
]))
csr = builder.sign(private_key, hashes.SHA256())

with open("homologacion.csr", "wb") as f:
    f.write(csr.public_bytes(serialization.Encoding.PEM))

print("Archivos homologacion.key y homologacion.csr generados exitosamente.")