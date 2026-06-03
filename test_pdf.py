import sys
import datetime
from app.services.pdf_factura import generar_y_subir_pdf_factura

# mock supabase
import app.db.supabase_client as sc
class MockSupabase:
    class storage:
        @classmethod
        def from_(cls, bucket):
            class Bucket:
                def upload(self, path, file, file_options):
                    print(f"Mock upload to {bucket}/{path}")
                    with open("test_out.pdf", "wb") as f:
                        f.write(file)
            return Bucket()

sc.get_supabase_service_client = lambda: MockSupabase()

factura_data = {
    "id": "test-id",
    "cliente_cuit_dni": "20111111112",
    "fecha": datetime.datetime.now().date().isoformat(),
    "punto_venta": 1,
    "tipo_comprobante": 6,
    "numero": 123,
    "imp_total": 1500.50,
    "cae": "12345678901234",
    "cae_vencimiento": datetime.datetime.now().date().isoformat()
}

config_fiscal = {
    "negocio_id": "test-negocio-id",
    "cuit": "20222222223",
    "razon_social": "Test Negocio",
    "condicion_fiscal": "responsable_inscripto"
}

res = generar_y_subir_pdf_factura(factura_data, {}, config_fiscal)
print("Resultado:", res)
