import io
import json
import base64
import qrcode # type: ignore
from reportlab.lib.pagesizes import A4  # type: ignore
from reportlab.pdfgen import canvas  # type: ignore
from reportlab.lib.units import cm  # type: ignore
from reportlab.lib.utils import ImageReader  # type: ignore
from app.db.supabase_client import get_supabase_service_client

def get_letra_factura(tipo_cbte: int) -> str:
    """
    Retorna la letra de la factura según el código de tipo de comprobante AFIP.
    """
    if tipo_cbte == 1:
        return "A"
    elif tipo_cbte == 6:
        return "B"
    elif tipo_cbte == 11:
        return "C"
    return "X"

def generar_y_subir_pdf_factura(factura_data: dict, venta_data: dict, config_fiscal: dict) -> str | None:
    """
    Genera un PDF de la factura con los datos de AFIP y lo sube al bucket 'facturas_pdf'.
    Retorna la ruta del archivo dentro del bucket (file_path) que se usará como pdf_url.
    """
    try:
        factura_id = str(factura_data.get("id"))
        negocio_id = str(config_fiscal.get("negocio_id"))
        
        # 1. Preparar datos para el QR de AFIP
        cuit_str = str(factura_data.get("cliente_cuit_dni", ""))
        tipo_doc_rec = 99 # Consumidor Final por defecto
        if cuit_str:
            if len(cuit_str) == 11:
                tipo_doc_rec = 80 # CUIT
            elif len(cuit_str) in [7, 8]:
                tipo_doc_rec = 96 # DNI
                
        nro_doc_rec = int(cuit_str) if cuit_str.isdigit() else 0
        
        qr_data = {
            "ver": 1,
            "fecha": str(factura_data.get("fecha", "")),
            "cuit": int(config_fiscal.get("cuit", 0)),
            "ptoVta": int(factura_data.get("punto_venta", 0)),
            "tipoCmp": int(factura_data.get("tipo_comprobante", 0)),
            "nroCmp": int(factura_data.get("numero", 0)),
            "importe": float(factura_data.get("imp_total", 0)),
            "moneda": "PES",
            "ctz": 1,
            "tipoDocRec": tipo_doc_rec,
            "nroDocRec": nro_doc_rec,
            "tipoCodAut": "E",
            "codAut": int(factura_data.get("cae", 0))
        }
        
        # 2. Generar el código QR
        qr_json = json.dumps(qr_data)
        qr_b64 = base64.b64encode(qr_json.encode('utf-8')).decode('utf-8')
        qr_url = f"https://www.afip.gob.ar/fe/qr/?p={qr_b64}"
        
        qr = qrcode.QRCode(version=1, box_size=4, border=1) # type: ignore
        qr.add_data(qr_url)
        qr.make(fit=True)
        img_qr = qr.make_image(fill_color="black", back_color="white")
        
        qr_buffer = io.BytesIO()
        img_qr.save(qr_buffer, format="PNG") # type: ignore
        qr_buffer.seek(0)
        qr_image = ImageReader(qr_buffer)
        
        # 3. Generar PDF
        pdf_buffer = io.BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=A4)
        width, height = A4
        
        # Encabezado
        c.setFont("Helvetica-Bold", 14)
        letra = get_letra_factura(int(factura_data.get("tipo_comprobante", 0)))
        c.drawString(2 * cm, height - 2 * cm, f"FACTURA {letra}")
        
        c.setFont("Helvetica", 10)
        c.drawString(2 * cm, height - 3 * cm, f"Razón Social: {config_fiscal.get('razon_social', '')}")
        c.drawString(2 * cm, height - 3.5 * cm, f"CUIT: {config_fiscal.get('cuit', '')}")
        cond_fiscal = str(config_fiscal.get('condicion_fiscal', '')).replace('_', ' ').title()
        c.drawString(2 * cm, height - 4 * cm, f"Condición Frente al IVA: {cond_fiscal}")
        
        # Datos Factura
        c.drawString(12 * cm, height - 3 * cm, f"Punto de Venta: {str(factura_data.get('punto_venta', '')).zfill(4)}")
        c.drawString(12 * cm, height - 3.5 * cm, f"Comp. Nro: {str(factura_data.get('numero', '')).zfill(8)}")
        c.drawString(12 * cm, height - 4 * cm, f"Fecha de Emisión: {factura_data.get('fecha', '')}")
        
        # Datos Cliente
        c.line(2 * cm, height - 4.5 * cm, 19 * cm, height - 4.5 * cm)
        c.drawString(2 * cm, height - 5.5 * cm, f"Cliente CUIT/DNI: {factura_data.get('cliente_cuit_dni', 'Consumidor Final')}")
        
        # Detalles de la Venta (simplificado)
        c.line(2 * cm, height - 6.5 * cm, 19 * cm, height - 6.5 * cm)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(2 * cm, height - 7.5 * cm, f"Total: $ {factura_data.get('imp_total', 0)}")
        
        # Datos AFIP al pie
        c.setFont("Helvetica", 9)
        c.drawString(12 * cm, 4 * cm, f"CAE N°: {factura_data.get('cae', '')}")
        c.drawString(12 * cm, 3.5 * cm, f"Fecha Vto. CAE: {factura_data.get('cae_vencimiento', '')}")
        
        # Dibujar QR al pie
        c.drawImage(qr_image, 2 * cm, 2 * cm, width=4*cm, height=4*cm)
        
        c.save()
        pdf_buffer.seek(0)
        
        # 4. Subir a Supabase Storage
        supabase = get_supabase_service_client()
        bucket_name = "facturas_pdf"
        file_path = f"{negocio_id}/{factura_id}.pdf"
        
        pdf_bytes = pdf_buffer.read()
        
        # Intentamos subir (esto reemplazará si ya existe usando 'upsert')
        supabase.storage.from_(bucket_name).upload(
            path=file_path,
            file=pdf_bytes,
            file_options={"content-type": "application/pdf", "upsert": "true"}  # type: ignore[arg-type]
        )
        
        # Devolver la ruta relativa (o url pública si el bucket no fuera privado)
        # La tabla facturas almacenará pdf_url = file_path
        return file_path
        
    except Exception as e:
        print(f"Error generando o subiendo PDF: {e}")
        return None
