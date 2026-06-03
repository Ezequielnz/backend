import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
from app.services.afip.afip_client import create_invoice, get_last_voucher_number

async def procesar_facturacion_afip(client: Any, negocio_id: str, venta_id: str, cliente_id: Optional[str], total: float, items: list):
    """
    Procesa la facturación ARCA para una venta.
    Devuelve los datos de la factura si fue exitosa, o None.
    """
    # Obtener config
    config_resp = client.table("configuracion_fiscal").select("*").eq("negocio_id", negocio_id).execute()
    if not config_resp.data:
        print("Facturación omitida: No hay config fiscal")
        return None
    config = config_resp.data[0]
    
    if not config.get("habilitada") or not config.get("cert_path") or not config.get("key_path"):
        print("Facturación omitida: Configuración no habilitada o faltan certificados")
        return None
        
    # Extraer datos de cliente
    doc_tipo = 99 # Consumidor Final por defecto
    doc_nro = 0
    if cliente_id:
        cliente_resp = client.table("clientes").select("tipo_documento,numero_documento").eq("id", cliente_id).execute()
        if cliente_resp.data:
            c_tipo = cliente_resp.data[0].get("tipo_documento")
            c_num = cliente_resp.data[0].get("numero_documento")
            if c_tipo == "CUIT" and c_num:
                doc_tipo = 80
                doc_nro = int(c_num.replace("-", ""))
            elif c_tipo == "DNI" and c_num:
                doc_tipo = 96
                doc_nro = int(c_num.replace(".", "").replace("-", ""))
    
    # Determinar Tipo de Comprobante
    condicion = config.get("condicion_fiscal")
    if condicion == "monotributista":
        cbte_tipo = 11 # Factura C
    else: # Responsable Inscripto
        if doc_tipo == 80:
            cbte_tipo = 1 # Factura A
        else:
            cbte_tipo = 6 # Factura B
            
    # Determinar concepto (1: Prod, 2: Serv, 3: Ambos)
    tiene_prod = any(i.get("tipo") == "producto" for i in items)
    tiene_serv = any(i.get("tipo") == "servicio" for i in items)
    if tiene_prod and tiene_serv: concepto = 3
    elif tiene_serv: concepto = 2
    else: concepto = 1
    
    ambiente = config.get("ambiente", "homologacion")
    if ambiente == "produccion":
        wsaa_wsdl = "https://wsaa.afip.gov.ar/ws/services/LoginCms?wsdl"
        wsfe_wsdl = "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"
    else:
        wsaa_wsdl = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?wsdl"
        wsfe_wsdl = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"
        
    cuit = config.get("cuit")
    pto_vta = config.get("punto_venta", 1)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        cert_path = Path(tmpdir) / "cert.crt"
        key_path = Path(tmpdir) / "key.key"
        
        try:
            cert_bytes = client.storage.from_("certificados_afip").download(config.get("cert_path"))
            with open(cert_path, "wb") as f: f.write(cert_bytes)
                
            key_bytes = client.storage.from_("certificados_afip").download(config.get("key_path"))
            with open(key_path, "wb") as f: f.write(key_bytes)
            
            # Obtener ultimo comprobante
            ult_cbte = await get_last_voucher_number(pto_vta, cbte_tipo, cert_path, key_path, wsaa_wsdl, wsfe_wsdl, cuit, "wsfe", client, negocio_id)
            siguiente = ult_cbte + 1
            
            # Preparar invoice_data
            imp_total = round(total, 2)
            invoice_data = {
                'punto_venta': pto_vta,
                'tipo_comprobante': cbte_tipo,
                'concepto': concepto,
                'doc_tipo': doc_tipo,
                'doc_nro': doc_nro,
                'cbte_desde': siguiente,
                'cbte_hasta': siguiente,
                'cbte_fecha': datetime.now().strftime('%Y%m%d'),
                'imp_total': imp_total,
                'imp_neto': imp_total,
                'imp_iva': 0.0,
                'imp_tot_conc': 0.0,
                'imp_op_ex': 0.0,
                'imp_trib': 0.0
            }
            
            if cbte_tipo in (1, 6): # Factura A o B (RI) requiere desglose de IVA (Asumimos 21%)
                neto = round(imp_total / 1.21, 2)
                iva = round(imp_total - neto, 2)
                invoice_data['imp_neto'] = neto
                invoice_data['imp_iva'] = iva
                invoice_data['iva'] = [{
                    'id': 5, # 21%
                    'base_imp': neto,
                    'importe': iva
                }]
                
            if concepto in (2, 3):
                invoice_data['fch_serv_desde'] = invoice_data['cbte_fecha']
                invoice_data['fch_serv_hasta'] = invoice_data['cbte_fecha']
                invoice_data['fch_vto_pago'] = invoice_data['cbte_fecha']
                
            # Llamar ARCA
            res = await create_invoice(invoice_data, cert_path, key_path, wsaa_wsdl, wsfe_wsdl, cuit, "wsfe", client, negocio_id)
            
            # Guardar factura
            cae = res.get("FeDetResp", {}).get("FECAEDetResponse", [{}])[0].get("CAE", "")
            cae_fch_vto = res.get("FeDetResp", {}).get("FECAEDetResponse", [{}])[0].get("CAEFchVto", "")
            
            factura_data = {
                "negocio_id": negocio_id,
                "venta_id": venta_id,
                "tipo_comprobante": cbte_tipo,
                "punto_venta": pto_vta,
                "numero": siguiente,
                "fecha": datetime.now().date().isoformat(),
                "cae": cae,
                "cae_vencimiento": datetime.strptime(cae_fch_vto, '%Y%m%d').date().isoformat() if cae_fch_vto else None,
                "imp_total": imp_total,
                "imp_neto": invoice_data.get('imp_neto', imp_total),
                "imp_iva": invoice_data.get('imp_iva', 0.0),
                "cliente_cuit_dni": str(doc_nro) if doc_nro > 0 else None,
                "estado": "emitida" if cae else "error",
                "error_detalle": None if cae else "Error al generar factura en AFIP"
            }
            factura_resp = client.table("facturas").insert(factura_data).execute()
            
            if factura_resp.data:
                factura_id = factura_resp.data[0]["id"]
                factura_data["id"] = factura_id
                
                # Import PDF Generator
                from app.services.pdf_factura import generar_y_subir_pdf_factura
                
                pdf_path = generar_y_subir_pdf_factura(factura_data, {}, config)
                if pdf_path:
                    client.table("facturas").update({"pdf_url": pdf_path}).eq("id", factura_id).execute()
                    factura_data["pdf_url"] = pdf_path
            
            return factura_data
            
        except Exception as e:
            print(f"Error procesando factura ARCA: {e}")
            return None
