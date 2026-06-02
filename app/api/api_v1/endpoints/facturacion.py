from fastapi import APIRouter, Depends, HTTPException, status, Request, Header, UploadFile, File, Form
from typing import Optional
from app.db.supabase_client import get_supabase_user_client
from app.core.permissions import check_subscription_access
from app.schemas.facturacion import ConfiguracionFiscalResponse, AfipStatusResponse

# Import ARCA client
from app.services.afip import get_server_status, get_last_voucher_number

router = APIRouter()

@router.get("/config", response_model=ConfiguracionFiscalResponse)
async def get_configuracion_fiscal(
    request: Request,
    business_id: str,
    authorization: str = Header(..., description="Bearer token"),
    subscription_check: bool = Depends(check_subscription_access)
):
    """
    Get fiscal configuration for a business.
    """
    client = get_supabase_user_client(authorization)
    
    # Check that business_id is valid via dependency (optional if already verified by frontend, but good practice)
    # The actual RLS should protect the data anyway.
    
    response = client.table("configuracion_fiscal").select("*").eq("negocio_id", business_id).execute()
    
    if not response.data or len(response.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró configuración fiscal para este negocio"
        )
        
    return response.data[0]

@router.post("/config", response_model=ConfiguracionFiscalResponse)
async def upsert_configuracion_fiscal(
    request: Request,
    business_id: str,
    cuit: str = Form(...),
    razon_social: str = Form(...),
    punto_venta: int = Form(1),
    condicion_fiscal: str = Form(...),
    ambiente: str = Form("homologacion"),
    habilitada: bool = Form(False),
    certificado: Optional[UploadFile] = File(None),
    clave_privada: Optional[UploadFile] = File(None),
    authorization: str = Header(..., description="Bearer token"),
    subscription_check: bool = Depends(check_subscription_access)
):
    """
    Update or create fiscal configuration and upload certs to Supabase Storage.
    """
    client = get_supabase_user_client(authorization)
    
    cert_path_db = None
    key_path_db = None
    
    # Check if a config already exists
    existing = client.table("configuracion_fiscal").select("*").eq("negocio_id", business_id).execute()
    if existing.data and len(existing.data) > 0:
        cert_path_db = existing.data[0].get("cert_path")
        key_path_db = existing.data[0].get("key_path")
        
    # Upload Certificate if provided
    if certificado:
        cert_data = await certificado.read()
        cert_filename = f"{business_id}/certificado.crt"
        client.storage.from_("certificados_afip").upload(
            file=cert_data, 
            path=cert_filename, 
            file_options={"upsert": "true", "content-type": "application/x-x509-ca-cert"}  # type: ignore
        )
        cert_path_db = cert_filename
        
    # Upload Private Key if provided
    if clave_privada:
        key_data = await clave_privada.read()
        key_filename = f"{business_id}/clave_privada.key"
        client.storage.from_("certificados_afip").upload(
            file=key_data, 
            path=key_filename, 
            file_options={"upsert": "true", "content-type": "application/pkcs8"}  # type: ignore
        )
        key_path_db = key_filename
        
    # Upsert data in configuracion_fiscal
    config_data = {
        "negocio_id": business_id,
        "cuit": cuit,
        "razon_social": razon_social,
        "punto_venta": punto_venta,
        "condicion_fiscal": condicion_fiscal,
        "ambiente": ambiente,
        "habilitada": habilitada
    }
    
    if cert_path_db:
        config_data["cert_path"] = cert_path_db
    if key_path_db:
        config_data["key_path"] = key_path_db
        
    response = client.table("configuracion_fiscal").upsert(
        config_data, 
        on_conflict="negocio_id"
    ).execute()
    
    if not response.data:
        raise HTTPException(status_code=400, detail="Error al guardar configuración")
        
    return response.data[0]

import tempfile
from pathlib import Path

@router.get("/status", response_model=AfipStatusResponse)
async def check_afip_status(
    request: Request,
    business_id: str,
    authorization: str = Header(..., description="Bearer token"),
    subscription_check: bool = Depends(check_subscription_access)
):
    """
    Check connection to ARCA using the uploaded certificates.
    Downloads certs from Storage to a temporary directory just for the check.
    """
    client = get_supabase_user_client(authorization)
    
    # Get config
    config_resp = client.table("configuracion_fiscal").select("*").eq("negocio_id", business_id).execute()
    if not config_resp.data or len(config_resp.data) == 0:
        raise HTTPException(status_code=404, detail="No hay configuración fiscal para este negocio")
        
    config = config_resp.data[0]
    
    if not config.get("cert_path") or not config.get("key_path"):
        raise HTTPException(status_code=400, detail="Faltan certificados (CRT/KEY) para probar conexión")
        
    # Choose WSDL based on environment
    ambiente = config.get("ambiente", "homologacion")
    if ambiente == "produccion":
        wsaa_wsdl = "https://wsaa.afip.gov.ar/ws/services/LoginCms?wsdl"
        wsfe_wsdl = "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"
    else:
        wsaa_wsdl = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?wsdl"
        wsfe_wsdl = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"
        
    cuit = config.get("cuit")
    pto_vta = config.get("punto_venta", 1)
    cond_fiscal = config.get("condicion_fiscal")
    
    # Use temporary directory to download certs
    with tempfile.TemporaryDirectory() as tmpdir:
        cert_path = Path(tmpdir) / "cert.crt"
        key_path = Path(tmpdir) / "key.key"
        
        try:
            # Download certs from Supabase Storage
            cert_bytes = client.storage.from_("certificados_afip").download(config.get("cert_path"))
            with open(cert_path, "wb") as f:
                f.write(cert_bytes)
                
            key_bytes = client.storage.from_("certificados_afip").download(config.get("key_path"))
            with open(key_path, "wb") as f:
                f.write(key_bytes)
                
            # Check server status
            status_data = await get_server_status(
                cert_path=cert_path,
                key_path=key_path,
                wsaa_wsdl=wsaa_wsdl,
                wsfe_wsdl=wsfe_wsdl,
                cuit=cuit
            )
            
            # Form response
            res = {
                "status": "OK" if status_data.get("appserver") == "OK" else "ERROR",
                "appserver": status_data.get("appserver", "Error"),
                "dbserver": status_data.get("dbserver", "Error"),
                "authserver": status_data.get("authserver", "Error"),
                "cuit": cuit,
                "punto_venta": pto_vta,
                "ultimo_comprobante_a": None,
                "ultimo_comprobante_b": None,
                "ultimo_comprobante_c": None
            }
            
            # Optional: query last vouchers if connection is OK
            if res["status"] == "OK":
                try:
                    if cond_fiscal == "responsable_inscripto":
                        # A = 1, B = 6
                        res["ultimo_comprobante_a"] = await get_last_voucher_number(pto_vta, 1, cert_path, key_path, wsaa_wsdl, wsfe_wsdl, cuit)
                        res["ultimo_comprobante_b"] = await get_last_voucher_number(pto_vta, 6, cert_path, key_path, wsaa_wsdl, wsfe_wsdl, cuit)
                    else:
                        # C = 11
                        res["ultimo_comprobante_c"] = await get_last_voucher_number(pto_vta, 11, cert_path, key_path, wsaa_wsdl, wsfe_wsdl, cuit)
                except Exception as e:
                    print(f"Error checking last vouchers: {e}")
            
            return res
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error validando conexión con ARCA: {str(e)}")