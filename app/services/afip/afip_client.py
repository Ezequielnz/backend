"""
Client service for interacting with ARCA Web Services.
"""
from datetime import datetime, timedelta
import os
from pathlib import Path
import xml.etree.ElementTree as ET
from zeep import Client
from zeep.transports import Transport
from zeep.exceptions import Fault
from typing import Dict, Optional, Tuple, Any, List
import requests
import urllib3
import ssl
import json
import random
import asyncio

from app.core.config import settings
from app.services.afip.ticket_access import get_access_ticket

# Desactivar advertencias de SSL inseguro (solo en desarrollo)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def generate_afip_soap_xml(operation: str, params: Dict[str, Any]) -> str:
    """
    Generate a properly formatted SOAP XML request for ARCA web services.
    
    Args:
        operation: SOAP operation name (e.g., 'FECAESolicitar')
        params: Parameters for the operation
        
    Returns:
        XML string for SOAP request
    """
    # ARCA SOAP namespaces
    namespaces = {
        'soap': 'http://schemas.xmlsoap.org/soap/envelope/',
        'afip': 'http://ar.gov.afip.dif.FEV1/'
    }
    
    # Create root element with namespaces
    root = ET.Element(f'{{{namespaces["soap"]}}}Envelope')
    
    # Add namespace declarations
    for prefix, uri in namespaces.items():
        root.set(f'xmlns:{prefix}', uri)
    
    # Create body
    body = ET.SubElement(root, f'{{{namespaces["soap"]}}}Body')
    
    # Create operation element
    op_elem = ET.SubElement(body, f'{{{namespaces["afip"]}}}{operation}')
    
    # Add parameters recursively
    def add_params(parent, params_dict):
        for key, value in params_dict.items():
            if isinstance(value, dict):
                child = ET.SubElement(parent, key)
                add_params(child, value)
            elif isinstance(value, list):
                for item in value:
                    child = ET.SubElement(parent, key)
                    if isinstance(item, dict):
                        add_params(child, item)
                    else:
                        child.text = str(item)
            else:
                child = ET.SubElement(parent, key)
                child.text = str(value)
    
    add_params(op_elem, params)
    
    # Convert to string
    return ET.tostring(root, encoding='utf-8', method='xml').decode('utf-8')

def parse_afip_error(response_xml: str) -> Dict[str, str]:
    """
    Parse ARCA error messages from SOAP response XML.
    
    Args:
        response_xml: SOAP response XML string
        
    Returns:
        Dictionary with error code and message
    """
    try:
        root = ET.fromstring(response_xml)
        
        # Check for SOAP fault
        soap_ns = '{http://schemas.xmlsoap.org/soap/envelope/}'
        fault = root.find(f'.//{soap_ns}Fault')
        
        if fault is not None:
            fault_code = fault.find('./faultcode')
            fault_string = fault.find('./faultstring')
            
            if fault_code is not None and fault_string is not None:
                return {
                    "code": fault_code.text or "",
                    "message": fault_string.text or ""
                }
        
        # Check for ARCA specific errors
        errors = []
        
        # Different paths where errors might be found in ARCA responses
        error_paths = [
            './/Errors',
            './/Errores',
            './/Err',
            './/Error'
        ]
        
        for path in error_paths:
            error_elem = root.find(path)
            if error_elem is not None:
                # Try to extract individual error elements
                for error in error_elem:
                    code = error.find('./Code') or error.find('./Codigo')
                    msg = error.find('./Msg') or error.find('./Mensaje')
                    
                    if code is not None and msg is not None:
                        errors.append(f"{code.text}: {msg.text}")
                    elif msg is not None:
                        errors.append(msg.text)
        
        if errors:
            return {
                "code": "ARCA-ERROR",
                "message": " | ".join(errors)
            }
        
        # Check for specific result fields
        result_elem = root.find('.//Resultado')
        if result_elem is not None and result_elem.text == "R":
            return {
                "code": "ARCA-REJECTED",
                "message": "ARCA rejected the request with no specific error details."
            }
        
        # If no specific error is found
        return {
            "code": "UNKNOWN",
            "message": "Unable to parse error details from the response."
        }
    except Exception as e:
        return {
            "code": "PARSE-ERROR",
            "message": f"Error parsing XML response: {str(e)}"
        }

async def send_raw_soap_request(wsdl_url: str, operation: str, params: Dict[str, Any]) -> Optional[str]:
    """
    Send a raw SOAP request to ARCA web services as a fallback when Zeep client fails.
    
    Args:
        wsdl_url: WSDL URL for the service
        operation: SOAP operation name
        params: Operation parameters
    
    Returns:
        XML response string or None if there was an error
    """
    try:
        # Generate the SOAP XML request
        xml_request = generate_afip_soap_xml(operation, params)
        
        # Create a session with custom SSL settings
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(max_retries=3)
        session.mount('https://', adapter)
        
        # Configure SSL
        context = ssl.create_default_context()
        context.set_ciphers('DEFAULT@SECLEVEL=1')
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        # Ignore SSL verification for ARCA's problematic certificates
        session.verify = False
        
        # Service URL from WSDL
        service_url = wsdl_url.replace('?WSDL', '')
        
        # Set required headers
        headers = {
            'Cache-Control': 'no-cache',
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': f'http://ar.gov.afip.dif.FEV1/{operation}',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive'
        }
        
        print(f"Sending raw SOAP request to {service_url}")
        print(f"Request headers: {headers}")
        if settings.ENVIRONMENT == "dev":
            print(f"Request body: {xml_request}")
        
        # Send the request
        response = session.post(
            service_url,
            data=xml_request,
            headers=headers,
            timeout=30
        )
        
        # Check for HTTP errors
        if response.status_code >= 400:
            # Parse error from response if available
            error_info = parse_afip_error(response.text)
            error_msg = f"HTTP error {response.status_code}: {error_info['message']}"
            print(error_msg)
            raise AfipError(error_msg, error_info['code'])
        
        # Check for ARCA errors in the response
        if "<Errors>" in response.text or "<Err>" in response.text or "faultstring" in response.text:
            error_info = parse_afip_error(response.text)
            error_msg = f"ARCA error: {error_info['message']}"
            print(error_msg)
            raise AfipError(error_msg, error_info['code'])
        
        # Log the response in development
        if settings.ENVIRONMENT == "dev":
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text}")
        
        return response.text
    except AfipError:
        # Re-raise existing AfipError instances
        raise
    except requests.RequestException as e:
        print(f"Error sending request: {str(e)}")
        
        # Check if we have a response to parse for more details
        if hasattr(e, 'response') and e.response is not None:
            error_info = parse_afip_error(e.response.text)
            error_msg = f"Request error: {error_info['message']}"
            raise AfipError(error_msg, error_info['code'])
        
        # Otherwise use the exception message
        raise AfipError(f"Request error: {str(e)}")
    except Exception as e:
        print(f"Error sending raw SOAP request: {str(e)}")
        
        # In development, return mock response
        if settings.ENVIRONMENT == "dev":
            print("DEV MODE: Returning mock SOAP response")
            if operation == "FECAESolicitar":
                now = datetime.now()
                exp_date = now + timedelta(days=10)
                
                return f"""<?xml version="1.0" encoding="utf-8"?>
                <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
                    <soap:Body>
                        <FECAESolicitarResponse xmlns="http://ar.gov.afip.dif.FEV1/">
                            <FECAESolicitarResult>
                                <FeCabResp>
                                    <Resultado>A</Resultado>
                                    <PtoVta>1</PtoVta>
                                    <CbteTipo>1</CbteTipo>
                                    <FchProceso>{now.strftime('%Y%m%d')}</FchProceso>
                                    <CantReg>1</CantReg>
                                    <Reproceso>N</Reproceso>
                                </FeCabResp>
                                <FeDetResp>
                                    <FECAEDetResponse>
                                        <Concepto>1</Concepto>
                                        <DocTipo>80</DocTipo>
                                        <DocNro>20111111112</DocNro>
                                        <CbteDesde>1</CbteDesde>
                                        <CbteHasta>1</CbteHasta>
                                        <CbteFch>{now.strftime('%Y%m%d')}</CbteFch>
                                        <CAE>12345678901234</CAE>
                                        <CAEFchVto>{exp_date.strftime('%Y%m%d')}</CAEFchVto>
                                        <Resultado>A</Resultado>
                                    </FECAEDetResponse>
                                </FeDetResp>
                            </FECAESolicitarResult>
                        </FECAESolicitarResponse>
                    </soap:Body>
                </soap:Envelope>"""
            else:
                return f"""<?xml version="1.0" encoding="utf-8"?>
                <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
                    <soap:Body>
                        <{operation}Response xmlns="http://ar.gov.afip.dif.FEV1/">
                            <{operation}Result>
                                <ResultGet>
                                    <Resultado>A</Resultado>
                                </ResultGet>
                            </{operation}Result>
                        </{operation}Response>
                    </soap:Body>
                </soap:Envelope>"""
        
        # In production, raise the error
        raise AfipError(f"Failed to send SOAP request: {str(e)}")

class AfipError(Exception):
    """Custom exception for ARCA service errors."""
    def __init__(self, message: str, code: Optional[str] = None):
        self.message = message
        self.code = code
        super().__init__(self.message)

async def get_client(service: str, cert_path: Path, key_path: Path, wsaa_wsdl: str, wsfe_wsdl: str, cuit: str, supabase_client: Any = None, negocio_id: Optional[str] = None) -> Tuple[Client, Dict[str, str]]:
    """
    Get a configured SOAP client for the specified ARCA service.
    
    Args:
        service: Service ID (e.g., 'wsfe')
        
    Returns:
        Tuple containing the SOAP client and authentication data
        
    Raises:
        AfipError: If authentication fails or service is unsupported
    """
    # Get authentication ticket
    ticket_data = await get_access_ticket(service, cert_path, key_path, wsaa_wsdl, cuit, supabase_client, negocio_id)
    
    if not ticket_data:
        raise AfipError("Failed to obtain ARCA authentication ticket")
    
    # Select the appropriate WSDL based on service
    wsdl_url = None
    if service == "wsfe":
        wsdl_url = wsfe_wsdl
    else:
        raise AfipError(f"Unsupported service: {service}")
    
    # Create client with custom transport configuration
    try:
        # Create custom session with SSL configuration
        session = requests.Session()
        
        # Configure SSL for weaker DH key support
        adapter = requests.adapters.HTTPAdapter(max_retries=3)
        session.mount('https://', adapter)
        
        # Create custom SSL context
        context = ssl.create_default_context()
        context.set_ciphers('DEFAULT@SECLEVEL=1')
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        # Apply context to HTTPS requests
        session.verify = False
        
        # Set specific headers required by ARCA
        headers = {
            'Cache-Control': 'no-cache',
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': f'http://ar.gov.afip.dif.FEV1/{service}',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive'
        }
        
        # Update session headers
        session.headers.update(headers)
        
        # Create Zeep transport with custom session
        transport = Transport(session=session)
        
        # Create client with custom transport
        client = Client(wsdl_url, transport=transport)
        
        # Set proper SOAPAction header based on operation
        if hasattr(client.service, '_binding'):
            operations = client.service._binding.ports[0].binding._operations
            for name, operation in operations.items():
                # Dynamically set SOAPAction for each operation
                operation.soap_action = f'http://ar.gov.afip.dif.FEV1/{name}'
        
        auth = {
            "Token": ticket_data["token"],
            "Sign": ticket_data["sign"],
            "Cuit": ticket_data["cuit"]
        }
        return client, auth
    except Exception as e:
        # En modo desarrollo, crear un cliente simulado
        if settings.ENVIRONMENT == "dev" and ("MOCKTOKEN" in ticket_data.get("token", "") or "Failed to create SOAP client" in str(e)):
            print(f"DEV MODE: Using mock ARCA client")
            # Devolver un cliente simulado para pruebas
            from types import SimpleNamespace
            mock_client = SimpleNamespace()
            mock_client.service = SimpleNamespace()
            
            # Simular los métodos del servicio
            mock_client.service.FEDummy = lambda: SimpleNamespace(AppServer="OK", DbServer="OK", AuthServer="OK")
            mock_client.service.FECompUltimoAutorizado = lambda **kwargs: SimpleNamespace(CbteNro=random.randint(1, 100))
            mock_client.service.FEParamGetTiposCbte = lambda **kwargs: json.loads('{"ResultGet": {"CbteTipo": [{"Id": "1", "Desc": "Factura A", "FchDesde": "20100917", "FchHasta": "NULL"}, {"Id": "6", "Desc": "Factura B", "FchDesde": "20100917", "FchHasta": "NULL"}]}}')
            mock_client.service.FEParamGetTiposConcepto = lambda **kwargs: json.loads('{"ResultGet": {"ConceptoTipo": [{"Id": "1", "Desc": "Productos", "FchDesde": "20100917", "FchHasta": "NULL"}, {"Id": "2", "Desc": "Servicios", "FchDesde": "20100917", "FchHasta": "NULL"}, {"Id": "3", "Desc": "Productos y Servicios", "FchDesde": "20100917", "FchHasta": "NULL"}]}}')
            
            # Simular FECAESolicitar
            def mock_fe_cae_solicitar(**kwargs):
                req = kwargs.get("FeCAEReq", {}) or {}
                det_req = req.get("FeDetReq", {}) if isinstance(req, dict) else {}
                det_list = det_req.get("FECAEDetRequest", [{}]) if isinstance(det_req, dict) else [{}]
                cbte_desde = det_list[0].get("CbteDesde", 1) if det_list and isinstance(det_list[0], dict) else 1
                
                cab_req = req.get("FeCabReq", {}) if isinstance(req, dict) else {}
                pto_vta = cab_req.get("PtoVta", 1) if isinstance(cab_req, dict) else 1
                cbte_tipo = cab_req.get("CbteTipo", 1) if isinstance(cab_req, dict) else 1
                
                return SimpleNamespace(
                    FeCabResp=SimpleNamespace(
                        Resultado="A",
                        CantReg=1,
                        PtoVta=pto_vta,
                        CbteTipo=cbte_tipo,
                        FchProceso=datetime.now().strftime("%Y%m%d"),
                        Reproceso="N"
                    ),
                    FeDetResp=SimpleNamespace(
                        FECAEDetResponse=[
                            SimpleNamespace(
                                Concepto=1,
                                DocTipo=80,
                                DocNro=20111111112,
                                CbteDesde=cbte_desde,
                                CbteHasta=cbte_desde,
                                CbteFch=datetime.now().strftime("%Y%m%d"),
                                Resultado="A",
                                CAE="12345678901234",
                                CAEFchVto=(datetime.now().replace(day=1) + timedelta(days=60)).strftime("%Y%m%d")
                            )
                        ]
                    )
                )
            
            mock_client.service.FECAESolicitar = mock_fe_cae_solicitar
            
            return mock_client, auth  # type: ignore[return-value]
            
        raise AfipError(f"Failed to create SOAP client: {str(e)}")

async def get_server_status(cert_path: Path, key_path: Path, wsaa_wsdl: str, wsfe_wsdl: str, cuit: str, service: str = "wsfe", supabase_client: Any = None, negocio_id: Optional[str] = None) -> Dict[str, str]:
    """
    Check the status of the ARCA service.
    
    Args:
        service: Service ID to check
        
    Returns:
        Dictionary with status information
    """
    try:
        client, _ = await get_client(service, cert_path, key_path, wsaa_wsdl, wsfe_wsdl, cuit, supabase_client, negocio_id)
        result = client.service.FEDummy()
        return {
            "appserver": getattr(result, "AppServer", "Unknown"),
            "dbserver": getattr(result, "DbServer", "Unknown"),
            "authserver": getattr(result, "AuthServer", "Unknown")
        }
    except Exception as e:
        raise AfipError(f"Failed to check server status: {str(e)}")

async def get_last_voucher_number(
    punto_venta: int, 
    tipo_comprobante: int,
    cert_path: Path,
    key_path: Path,
    wsaa_wsdl: str,
    wsfe_wsdl: str,
    cuit: str,
    service: str = "wsfe",
    supabase_client: Any = None,
    negocio_id: Optional[str] = None
) -> int:
    """
    Get the last voucher number for the specified sales point and voucher type.
    
    Args:
        punto_venta: Sales point number
        tipo_comprobante: Voucher type code
        service: Service ID
        
    Returns:
        Last voucher number
    """
    try:
        client, auth = await get_client(service, cert_path, key_path, wsaa_wsdl, wsfe_wsdl, cuit, supabase_client, negocio_id)
        result = client.service.FECompUltimoAutorizado(
            Auth=auth,
            PtoVta=punto_venta,
            CbteTipo=tipo_comprobante
        )
        
        if hasattr(result, "Errors") and result.Errors:
            error_msg = ", ".join(f"{error.Code}: {error.Msg}" for error in result.Errors)
            raise AfipError(f"ARCA error: {error_msg}")
            
        return result.CbteNro
    except Fault as fault:
        raise AfipError(f"SOAP fault: {str(fault)}")
    except Exception as e:
        raise AfipError(f"Failed to get last voucher number: {str(e)}")

async def get_invoice_types(cert_path: Path, key_path: Path, wsaa_wsdl: str, wsfe_wsdl: str, cuit: str, service: str = "wsfe") -> Dict[str, Any]:
    """
    Get available invoice types from ARCA.
    
    Args:
        service: Service ID
        
    Returns:
        Dictionary with invoice types information
    """
    try:
        client, auth = await get_client(service, cert_path, key_path, wsaa_wsdl, wsfe_wsdl, cuit)
        result = client.service.FEParamGetTiposCbte(Auth=auth)
        
        if hasattr(result, "Errors") and result.Errors:
            error_msg = ", ".join(f"{error.Code}: {error.Msg}" for error in result.Errors)
            raise AfipError(f"ARCA error: {error_msg}")
            
        return result
    except Exception as e:
        raise AfipError(f"Failed to get invoice types: {str(e)}")

async def get_concept_types(cert_path: Path, key_path: Path, wsaa_wsdl: str, wsfe_wsdl: str, cuit: str, service: str = "wsfe") -> Dict[str, Any]:
    """
    Get available concept types from ARCA.
    
    Args:
        service: Service ID
        
    Returns:
        Dictionary with concept types information
    """
    try:
        client, auth = await get_client(service, cert_path, key_path, wsaa_wsdl, wsfe_wsdl, cuit)
        result = client.service.FEParamGetTiposConcepto(Auth=auth)
        
        if hasattr(result, "Errors") and result.Errors:
            error_msg = ", ".join(f"{error.Code}: {error.Msg}" for error in result.Errors)
            raise AfipError(f"ARCA error: {error_msg}")
            
        return result
    except Exception as e:
        raise AfipError(f"Failed to get concept types: {str(e)}")

async def get_document_types(cert_path: Path, key_path: Path, wsaa_wsdl: str, wsfe_wsdl: str, cuit: str, service: str = "wsfe") -> Dict[str, Any]:
    """
    Get available document types from ARCA.
    
    Args:
        service: Service ID
        
    Returns:
        Dictionary with document types information
    """
    try:
        client, auth = await get_client(service, cert_path, key_path, wsaa_wsdl, wsfe_wsdl, cuit)
        result = client.service.FEParamGetTiposDoc(Auth=auth)
        
        if hasattr(result, "Errors") and result.Errors:
            error_msg = ", ".join(f"{error.Code}: {error.Msg}" for error in result.Errors)
            raise AfipError(f"ARCA error: {error_msg}")
            
        return result
    except Exception as e:
        raise AfipError(f"Failed to get document types: {str(e)}")

async def get_tax_types(cert_path: Path, key_path: Path, wsaa_wsdl: str, wsfe_wsdl: str, cuit: str, service: str = "wsfe") -> Dict[str, Any]:
    """
    Get available tax types from ARCA.
    
    Args:
        service: Service ID
        
    Returns:
        Dictionary with tax types information
    """
    try:
        client, auth = await get_client(service, cert_path, key_path, wsaa_wsdl, wsfe_wsdl, cuit)
        result = client.service.FEParamGetTiposIva(Auth=auth)
        
        if hasattr(result, "Errors") and result.Errors:
            error_msg = ", ".join(f"{error.Code}: {error.Msg}" for error in result.Errors)
            raise AfipError(f"ARCA error: {error_msg}")
            
        return result
    except Exception as e:
        raise AfipError(f"Failed to get tax types: {str(e)}")

async def get_currency_types(cert_path: Path, key_path: Path, wsaa_wsdl: str, wsfe_wsdl: str, cuit: str, service: str = "wsfe") -> Dict[str, Any]:
    """
    Get available currency types from ARCA.
    
    Args:
        service: Service ID
        
    Returns:
        Dictionary with currency types information
    """
    try:
        client, auth = await get_client(service, cert_path, key_path, wsaa_wsdl, wsfe_wsdl, cuit)
        result = client.service.FEParamGetTiposMonedas(Auth=auth)
        
        if hasattr(result, "Errors") and result.Errors:
            error_msg = ", ".join(f"{error.Code}: {error.Msg}" for error in result.Errors)
            raise AfipError(f"ARCA error: {error_msg}")
            
        return result
    except Exception as e:
        raise AfipError(f"Failed to get currency types: {str(e)}")

async def get_optional_types(cert_path: Path, key_path: Path, wsaa_wsdl: str, wsfe_wsdl: str, cuit: str, service: str = "wsfe") -> Dict[str, Any]:
    """
    Get available optional data types from ARCA.
    
    Args:
        service: Service ID
        
    Returns:
        Dictionary with optional data types information
    """
    try:
        client, auth = await get_client(service, cert_path, key_path, wsaa_wsdl, wsfe_wsdl, cuit)
        result = client.service.FEParamGetTiposOpcional(Auth=auth)
        
        if hasattr(result, "Errors") and result.Errors:
            error_msg = ", ".join(f"{error.Code}: {error.Msg}" for error in result.Errors)
            raise AfipError(f"ARCA error: {error_msg}")
            
        return result
    except Exception as e:
        raise AfipError(f"Failed to get optional data types: {str(e)}")

async def create_invoice(
    invoice_data: Dict[str, Any],
    cert_path: Path,
    key_path: Path,
    wsaa_wsdl: str,
    wsfe_wsdl: str,
    cuit: str,
    service: str = "wsfe",
    supabase_client: Any = None,
    negocio_id: Optional[str] = None
) -> Any:
    """
    Create an electronic invoice through ARCA.
    
    Args:
        invoice_data: Dictionary containing invoice data
        service: Service ID
        
    Returns:
        Dictionary with ARCA response
    """
    max_retries = 3
    retry_count = 0
    last_error = None
    used_fallback = False
    
    while retry_count < max_retries:
        try:
            if used_fallback:
                # If we already tried the Zeep client and it failed, use the raw SOAP request directly
                print("Using raw SOAP request fallback for FECAESolicitar")
                
                # Prepare authentication data
                ticket_data = await get_access_ticket(service, cert_path, key_path, wsaa_wsdl, cuit, supabase_client, negocio_id)
                if not ticket_data:
                    raise AfipError("Failed to obtain ARCA authentication ticket")
                
                auth = {
                    "Token": ticket_data["token"],
                    "Sign": ticket_data["sign"],
                    "Cuit": ticket_data["cuit"]
                }
                
                # Prepare request structure
                req = {
                    'Auth': auth,
                    'FeCAEReq': {
                        'FeCabReq': {
                            'CantReg': 1,
                            'PtoVta': invoice_data['punto_venta'],
                            'CbteTipo': invoice_data['tipo_comprobante']
                        },
                        'FeDetReq': {
                            'FECAEDetRequest': [{
                                'Concepto': invoice_data['concepto'],
                                'DocTipo': invoice_data['doc_tipo'],
                                'DocNro': invoice_data['doc_nro'],
                                'CbteDesde': invoice_data['cbte_desde'],
                                'CbteHasta': invoice_data['cbte_hasta'],
                                'CbteFch': invoice_data['cbte_fecha'].replace('-', ''),
                                'ImpTotal': float(invoice_data['imp_total']),
                                'ImpTotConc': float(invoice_data.get('imp_tot_conc', 0)),
                                'ImpNeto': float(invoice_data.get('imp_neto', 0)),
                                'ImpOpEx': float(invoice_data.get('imp_op_ex', 0)),
                                'ImpIVA': float(invoice_data.get('imp_iva', 0)),
                                'ImpTrib': float(invoice_data.get('imp_trib', 0)),
                                'FchServDesde': invoice_data.get('fch_serv_desde', ''),
                                'FchServHasta': invoice_data.get('fch_serv_hasta', ''),
                                'FchVtoPago': invoice_data.get('fch_vto_pago', ''),
                                'MonId': invoice_data.get('moneda_id', 'PES'),
                                'MonCotiz': float(invoice_data.get('moneda_cotiz', 1)),
                            }]
                        }
                    }
                }
                
                # Add IVA information if present
                if 'iva' in invoice_data and invoice_data['iva']:
                    alicuotas_iva = []
                    for item in invoice_data['iva']:
                        alicuotas_iva.append({
                            'Id': int(item['id']),
                            'BaseImp': float(item['base_imp']),
                            'Importe': float(item['importe'])
                        })
                    
                    req['FeCAEReq']['FeDetReq']['FECAEDetRequest'][0]['Iva'] = {
                        'AlicIva': alicuotas_iva
                    }
                
                # Add tributes if present
                if 'tributos' in invoice_data and invoice_data['tributos']:
                    tributos = []
                    for item in invoice_data['tributos']:
                        tributos.append({
                            'Id': int(item['id']),
                            'Desc': item.get('desc', ''),
                            'BaseImp': float(item['base_imp']),
                            'Alic': float(item['alic']),
                            'Importe': float(item['importe'])
                        })
                    
                    req['FeCAEReq']['FeDetReq']['FECAEDetRequest'][0]['Tributos'] = {
                        'Tributo': tributos
                    }
                
                # Add optional data if present    
                if 'opcionales' in invoice_data and invoice_data['opcionales']:
                    opcionales = []
                    for item in invoice_data['opcionales']:
                        opcionales.append({
                            'Id': item['id'],
                            'Valor': item['valor']
                        })
                    
                    req['FeCAEReq']['FeDetReq']['FECAEDetRequest'][0]['Opcionales'] = {
                        'Opcional': opcionales
                    }
                
                # Add related vouchers if present
                if 'cbtes_asoc' in invoice_data and invoice_data['cbtes_asoc']:
                    cbtes_asoc = []
                    for item in invoice_data['cbtes_asoc']:
                        cbtes_asoc.append({
                            'Tipo': int(item['tipo']),
                            'PtoVta': int(item['pto_vta']),
                            'Nro': int(item['nro'])
                        })
                    
                    req['FeCAEReq']['FeDetReq']['FECAEDetRequest'][0]['CbtesAsoc'] = {
                        'CbteAsoc': cbtes_asoc
                    }
                
                # Send the raw SOAP request
                xml_response = await send_raw_soap_request(wsfe_wsdl, "FECAESolicitar", req)
                if not xml_response:
                    raise AfipError("Failed to get response from ARCA")
                
                # Parse the response XML
                try:
                    root = ET.fromstring(xml_response)
                    namespaces = {
                        'soap': 'http://schemas.xmlsoap.org/soap/envelope/',
                        'ns': 'http://ar.gov.afip.dif.FEV1/'
                    }
                    
                    # Extract data from XML
                    response_path = './/ns:FECAESolicitarResult'
                    result_elem = root.find(response_path, namespaces)
                    
                    if result_elem is None:
                        raise AfipError("Invalid ARCA response format")
                    
                    # Create a response object similar to the Zeep client response
                    from types import SimpleNamespace
                    
                    # Extract header data
                    # Helper for safe XML text extraction
                    def get_xml_text(parent, tag, default=""):
                        if parent is not None:
                            el = parent.find(tag)
                            if el is not None and el.text is not None:
                                return el.text
                        return default

                    # Extract header data
                    cab_resp = result_elem.find('.//FeCabResp')
                    resultado = get_xml_text(cab_resp, 'Resultado', "R")
                    pto_vta = int(get_xml_text(cab_resp, 'PtoVta', "0"))
                    cbte_tipo = int(get_xml_text(cab_resp, 'CbteTipo', "0"))
                    fch_proceso = get_xml_text(cab_resp, 'FchProceso', "")
                    cant_reg = int(get_xml_text(cab_resp, 'CantReg', "0"))
                    reproceso = get_xml_text(cab_resp, 'Reproceso', "N")
                    
                    # Extract detail data
                    det_resp = result_elem.find('.//FECAEDetResponse')
                    concepto = int(get_xml_text(det_resp, 'Concepto', "0"))
                    doc_tipo = int(get_xml_text(det_resp, 'DocTipo', "0"))
                    doc_nro = int(get_xml_text(det_resp, 'DocNro', "0"))
                    cbte_desde = int(get_xml_text(det_resp, 'CbteDesde', "0"))
                    cbte_hasta = int(get_xml_text(det_resp, 'CbteHasta', "0"))
                    cbte_fch = get_xml_text(det_resp, 'CbteFch', "")
                    cae = get_xml_text(det_resp, 'CAE', "")
                    cae_fch_vto = get_xml_text(det_resp, 'CAEFchVto', "")
                    resultado_det = get_xml_text(det_resp, 'Resultado', "R")
                    
                    # Create result object
                    result = SimpleNamespace()
                    result.FeCabResp = SimpleNamespace(
                        Resultado=resultado,
                        PtoVta=pto_vta,
                        CbteTipo=cbte_tipo,
                        FchProceso=fch_proceso,
                        CantReg=cant_reg,
                        Reproceso=reproceso
                    )
                    
                    detail_response = SimpleNamespace(
                        Concepto=concepto,
                        DocTipo=doc_tipo,
                        DocNro=doc_nro,
                        CbteDesde=cbte_desde,
                        CbteHasta=cbte_hasta,
                        CbteFch=cbte_fch,
                        CAE=cae,
                        CAEFchVto=cae_fch_vto,
                        Resultado=resultado_det
                    )
                    
                    result.FeDetResp = SimpleNamespace(
                        FECAEDetResponse=[detail_response]
                    )
                    
                    # Log the response
                    print(f"Parsed ARCA response: CAE={cae}, Resultado={resultado_det}")
                    
                    return result
                except Exception as xml_error:
                    print(f"Error parsing ARCA response XML: {str(xml_error)}")
                    raise AfipError(f"Error parsing ARCA response: {str(xml_error)}")
            else:
                # Try with the Zeep client first
                client, auth = await get_client(service, cert_path, key_path, wsaa_wsdl, wsfe_wsdl, cuit, supabase_client, negocio_id)
                
                # Update SOAPAction header specifically for this operation
                if hasattr(client.transport, 'session'):
                    client.transport.session.headers.update({
                        'SOAPAction': 'http://ar.gov.afip.dif.FEV1/FECAESolicitar'
                    })
                
                # Estructura exacta según documentación de ARCA
                req = {
                    'Auth': auth,
                    'FeCAEReq': {
                        'FeCabReq': {
                            'CantReg': 1,  # Cantidad de comprobantes a registrar
                            'PtoVta': invoice_data['punto_venta'],  # Punto de venta
                            'CbteTipo': invoice_data['tipo_comprobante']  # Tipo de comprobante (1=Factura A, 6=Factura B)
                        },
                        'FeDetReq': {
                            'FECAEDetRequest': [{
                                'Concepto': invoice_data['concepto'],  # Concepto: 1=Productos, 2=Servicios, 3=Productos y Servicios
                                'DocTipo': invoice_data['doc_tipo'],  # Tipo de documento del comprador: 80=CUIT, 96=DNI
                                'DocNro': invoice_data['doc_nro'],  # Número de documento del comprador
                                'CbteDesde': invoice_data['cbte_desde'],  # Número de comprobante desde
                                'CbteHasta': invoice_data['cbte_hasta'],  # Número de comprobante hasta (igual al anterior para comprobante único)
                                'CbteFch': invoice_data['cbte_fecha'].replace('-', ''),  # Fecha del comprobante formato AAAAMMDD
                                'ImpTotal': float(invoice_data['imp_total']),  # Importe total del comprobante
                                'ImpTotConc': float(invoice_data.get('imp_tot_conc', 0)),  # Importe neto no gravado
                                'ImpNeto': float(invoice_data.get('imp_neto', 0)),  # Importe neto gravado
                                'ImpOpEx': float(invoice_data.get('imp_op_ex', 0)),  # Importe exento de IVA
                                'ImpIVA': float(invoice_data.get('imp_iva', 0)),  # Importe total de IVA
                                'ImpTrib': float(invoice_data.get('imp_trib', 0)),  # Importe total de tributos
                                'FchServDesde': invoice_data.get('fch_serv_desde', ''),  # Fecha inicio del servicio (servicios)
                                'FchServHasta': invoice_data.get('fch_serv_hasta', ''),  # Fecha fin del servicio (servicios)
                                'FchVtoPago': invoice_data.get('fch_vto_pago', ''),  # Fecha de vencimiento del pago (servicios)
                                'MonId': invoice_data.get('moneda_id', 'PES'),  # Moneda: PES=Pesos Argentinos
                                'MonCotiz': float(invoice_data.get('moneda_cotiz', 1)),  # Cotización de la moneda (1 para pesos)
                            }]
                        }
                    }
                }
                
                # Agregar información de IVA si está presente
                if 'iva' in invoice_data and invoice_data['iva']:
                    # Formatear los datos de IVA según el formato requerido por ARCA
                    alicuotas_iva = []
                    for item in invoice_data['iva']:
                        alicuotas_iva.append({
                            'Id': int(item['id']),                # ID de alícuota (5=21%, 4=10.5%, 6=27%, 3=0%)
                            'BaseImp': float(item['base_imp']),   # Base imponible
                            'Importe': float(item['importe'])     # Importe de IVA
                        })
                    
                    req['FeCAEReq']['FeDetReq']['FECAEDetRequest'][0]['Iva'] = {
                        'AlicIva': alicuotas_iva
                    }
                    
                # Agregar tributos (impuestos provinciales, etc.) si están presentes
                if 'tributos' in invoice_data and invoice_data['tributos']:
                    tributos = []
                    for item in invoice_data['tributos']:
                        tributos.append({
                            'Id': int(item['id']),                # ID del tributo
                            'Desc': item.get('desc', ''),         # Descripción
                            'BaseImp': float(item['base_imp']),   # Base imponible
                            'Alic': float(item['alic']),          # Alícuota
                            'Importe': float(item['importe'])     # Importe del tributo
                        })
                    
                    req['FeCAEReq']['FeDetReq']['FECAEDetRequest'][0]['Tributos'] = {
                        'Tributo': tributos
                    }
                    
                # Agregar opcionales si están presentes
                if 'opcionales' in invoice_data and invoice_data['opcionales']:
                    opcionales = []
                    for item in invoice_data['opcionales']:
                        opcionales.append({
                            'Id': item['id'],      # ID del opcional
                            'Valor': item['valor'] # Valor del opcional
                        })
                    
                    req['FeCAEReq']['FeDetReq']['FECAEDetRequest'][0]['Opcionales'] = {
                        'Opcional': opcionales
                    }

                # Agregar comprobantes asociados (para notas de crédito/débito) si están presentes
                if 'cbtes_asoc' in invoice_data and invoice_data['cbtes_asoc']:
                    cbtes_asoc = []
                    for item in invoice_data['cbtes_asoc']:
                        cbtes_asoc.append({
                            'Tipo': int(item['tipo']),           # Tipo de comprobante asociado
                            'PtoVta': int(item['pto_vta']),      # Punto de venta del comprobante asociado
                            'Nro': int(item['nro'])              # Número del comprobante asociado
                        })
                    
                    req['FeCAEReq']['FeDetReq']['FECAEDetRequest'][0]['CbtesAsoc'] = {
                        'CbteAsoc': cbtes_asoc
                    }
                    
                print(f"Enviando solicitud de factura a ARCA: {req}")
                
                # Log request XML for debugging
                if hasattr(client.transport, 'session'):
                    client.settings.strict = False  # type: ignore
                    _original_post = client.transport.session.post
                    
                    def _capturing_post(*args, **kwargs):
                        print(f"SOAP Request URL: {args[0]}")
                        if 'data' in kwargs:
                            print(f"SOAP Request XML: {kwargs['data']}")
                        return _original_post(*args, **kwargs)
                    
                    client.transport.session.post = _capturing_post  # type: ignore[assignment]
                    
                # Llamar al servicio web de ARCA
                result = client.service.FECAESolicitar(**req)
                
                # Restore original post method
                if hasattr(client.transport, 'session') and '_original_post' in locals():
                    client.transport.session.post = _original_post  # type: ignore[assignment]
                
                if hasattr(result, "Errors") and result.Errors:
                    error_msg = ", ".join(f"{error.Code}: {error.Msg}" for error in result.Errors)
                    raise AfipError(f"ARCA error: {error_msg}")
                    
                # Log response for debugging
                print(f"Respuesta de ARCA: CAE={getattr(result.FeDetResp.FECAEDetResponse[0], 'CAE', 'No CAE')}, " 
                      f"Resultado={getattr(result.FeDetResp.FECAEDetResponse[0], 'Resultado', 'Desconocido')}")
                    
                return result
                
        except Fault as fault:
            print(f"SOAP Fault: {str(fault)}")
            last_error = f"SOAP fault: {str(fault)}"
            
            # If Zeep client failed, try with raw SOAP request
            if not used_fallback:
                used_fallback = True
                print("Switching to raw SOAP request fallback")
                continue
                
            retry_count += 1
            if retry_count < max_retries:
                print(f"Retrying... Attempt {retry_count} of {max_retries}")
                await asyncio.sleep(2 * retry_count)  # Exponential backoff
            else:
                raise AfipError(last_error)
        except Exception as e:
            print(f"Error creating invoice: {str(e)}")
            last_error = f"Failed to create invoice: {str(e)}"
            
            # If Zeep client failed, try with raw SOAP request
            if not used_fallback:
                used_fallback = True
                print("Switching to raw SOAP request fallback after error")
                continue
                
            retry_count += 1
            if retry_count < max_retries:
                print(f"Retrying... Attempt {retry_count} of {max_retries}")
                await asyncio.sleep(2 * retry_count)  # Exponential backoff
            else:
                raise AfipError(last_error)

async def get_invoice_info(
    punto_venta: int,
    tipo_comprobante: int,
    nro_comprobante: int,
    cert_path: Path,
    key_path: Path,
    wsaa_wsdl: str,
    wsfe_wsdl: str,
    cuit: str,
    service: str = "wsfe"
) -> Any:
    """
    Get information about a specific invoice.
    
    Args:
        punto_venta: Sales point number
        tipo_comprobante: Invoice type code
        nro_comprobante: Invoice number
        service: Service ID
        
    Returns:
        Dictionary with invoice information
    """
    try:
        client, auth = await get_client(service, cert_path, key_path, wsaa_wsdl, wsfe_wsdl, cuit)
        result = client.service.FECompConsultar(
            Auth=auth,
            FeCompConsReq={
                'PtoVta': punto_venta,
                'CbteTipo': tipo_comprobante,
                'CbteNro': nro_comprobante
            }
        )
        
        if hasattr(result, "Errors") and result.Errors:
            error_msg = ", ".join(f"{error.Code}: {error.Msg}" for error in result.Errors)
            raise AfipError(f"ARCA error: {error_msg}")
            
        return result
    except Fault as fault:
        raise AfipError(f"SOAP fault: {str(fault)}")
    except Exception as e:
        raise AfipError(f"Failed to get invoice information: {str(e)}")

# Add more ARCA Web Services functions as needed 