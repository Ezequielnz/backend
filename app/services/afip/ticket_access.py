"""
Service for handling ARCA authentication tickets (TA).
"""
import base64
import datetime
import os
import ssl
from pathlib import Path
from typing import Dict, Optional, Any
from lxml import etree
from zeep import Client
from zeep.transports import Transport
import requests
import urllib3
from requests.adapters import HTTPAdapter
from cryptography.hazmat.primitives.serialization import load_pem_private_key
import urllib3
import ssl

class CustomSSLAdapter(HTTPAdapter):
    def __init__(self, ssl_context=None, **kwargs):
        self.ssl_context = ssl_context
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_context'] = self.ssl_context
        return super().init_poolmanager(*args, **kwargs)
        
    def proxy_manager_for(self, *args, **kwargs):
        kwargs['ssl_context'] = self.ssl_context
        return super().proxy_manager_for(*args, **kwargs)

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import pkcs7

from app.core.config import settings

# Desactivar advertencias de SSL inseguro (solo en desarrollo)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Cache for tickets to avoid unnecessary WSAA calls
ticket_cache: Dict[str, Dict[str, Any]] = {}

async def sign_tra(tra: str, cert_path: Path, key_path: Path) -> Optional[str]:
    """
    Sign a TRA with PKCS7 and return it in Base64 format.
    
    Args:
        tra: The XML TRA to sign
        cert_path: Path to the certificate file
        key_path: Path to the private key file
        
    Returns:
        Base64 encoded signed data or None if there was an error
    """
    try:
        # Verificar si los archivos existen
        if not cert_path.exists() or not key_path.exists():
            print(f"Certificate ({cert_path.exists()}) or key ({key_path.exists()}) file not found")
            # En entorno de desarrollo, generar firma ficticia para pruebas
            if settings.ENVIRONMENT == "dev":
                print("DEV MODE: Generating mock signature for testing")
                mock_data = "MOCKSIGNATURE_FOR_TESTING_ONLY_NOT_VALID"
                return base64.b64encode(mock_data.encode()).decode()
            return None
            
        # Cargar y verificar el certificado y la clave
        try:
            with open(key_path, "rb") as key_file:
                private_key = load_pem_private_key(key_file.read(), password=None, backend=default_backend())
            
            with open(cert_path, "rb") as cert_file:
                certificate = load_pem_x509_certificate(cert_file.read(), default_backend())
        except Exception as cert_error:
            print(f"Error loading certificate or key: {cert_error}")
            # En entorno de desarrollo, generar firma ficticia para pruebas
            if settings.ENVIRONMENT == "dev":
                print("DEV MODE: Generating mock signature for testing")
                mock_data = "MOCKSIGNATURE_FOR_TESTING_ONLY_NOT_VALID"
                return base64.b64encode(mock_data.encode()).decode()
            return None

        # Sign the XML with PKCS#7 and DER encoding
        signer = pkcs7.PKCS7SignatureBuilder().set_data(tra.encode()).add_signer(
            certificate, private_key, hashes.SHA256()  # type: ignore[arg-type]
        )
        signed_der = signer.sign(
            options=[pkcs7.PKCS7Options.Binary], encoding=Encoding.DER
        )

        return base64.b64encode(signed_der).decode()
    except Exception as e:
        print(f"Error signing XML: {e}")
        # En entorno de desarrollo, generar firma ficticia para pruebas
        if settings.ENVIRONMENT == "dev":
            print("DEV MODE: Generating mock signature for testing")
            mock_data = "MOCKSIGNATURE_FOR_TESTING_ONLY_NOT_VALID"
            return base64.b64encode(mock_data.encode()).decode()
        return None

async def create_login_ticket(service: str) -> str:
    """
    Create a login ticket request XML for ARCA.
    
    Args:
        service: Service ID (e.g., 'wsfe')
        
    Returns:
        XML login ticket request
    """
    # Usar timezone explícito de Argentina (UTC-3) para evitar problemas de sincronización
    tz_ar = datetime.timezone(datetime.timedelta(hours=-3))
    now = datetime.datetime.now(tz_ar)
    
    unique_id = str(int(now.timestamp()))
    
    # Restar 5 minutos para tolerar desfasaje del servidor y remover microsegundos
    gen_time = (now - datetime.timedelta(minutes=5)).replace(microsecond=0).isoformat()
    exp_time = (now + datetime.timedelta(hours=12)).replace(microsecond=0).isoformat()
    
    # Build the XML
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <loginTicketRequest>
        <header>
            <uniqueId>{unique_id}</uniqueId>
            <generationTime>{gen_time}</generationTime>
            <expirationTime>{exp_time}</expirationTime>
        </header>
        <service>{service}</service>
    </loginTicketRequest>"""
    
    return xml

async def send_ticket_request(signed_data: str, wsaa_wsdl: str) -> Optional[str]:
    """
    Send a signed login ticket request to WSAA.
    
    Args:
        signed_data: Base64 encoded signed request
        
    Returns:
        XML response from WSAA or None if there was an error
    """
    try:
        # En entorno de desarrollo, generar una respuesta ficticia para pruebas
        if settings.ENVIRONMENT == "dev" and "MOCKSIGNATURE" in signed_data:
            print("DEV MODE: Generating mock WSAA response for testing")
            # Crear una respuesta XML ficticia con token y sign para pruebas
            now = datetime.datetime.now()
            expiration = now + datetime.timedelta(hours=12)
            mock_response = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<loginTicketResponse version="1.0">
    <header>
        <source>CN=wsaahomo, O=ARCA, C=AR, SERIALNUMBER=CUIT 33693450239</source>
        <destination>SERIALNUMBER=CUIT 20283176789, CN=test</destination>
        <uniqueId>{int(now.timestamp())}</uniqueId>
        <generationTime>{now.isoformat()}</generationTime>
        <expirationTime>{expiration.isoformat()}</expirationTime>
    </header>
    <credentials>
        <token>MOCKTOKEN123456789</token>
        <sign>MOCKSIGN987654321</sign>
    </credentials>
</loginTicketResponse>"""
            
            # Guardar en un archivo para simular el comportamiento normal
            os.makedirs("app/services/tickets", exist_ok=True)
            
            response_filename = f"app/services/tickets/{now.strftime('%y%m%d%H%M')}-loginTicketResponse.xml"
            
            with open(response_filename, "w", encoding="utf-8") as f:
                f.write(mock_response)
            
            return mock_response
    
        # Crear un contexto SSL personalizado
        context = ssl.create_default_context()
        context.set_ciphers('DEFAULT@SECLEVEL=0')  # Permitir cifrados menos seguros
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        # Crear una sesión personalizada con configuración SSL ajustada
        session = requests.Session()
        
        # Configurar la sesión con el adaptador personalizado
        adapter = CustomSSLAdapter(ssl_context=context, max_retries=3)
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        
        # Aplicar el contexto a las peticiones HTTPS
        session.verify = False
        
        # Crear el transporte para Zeep con la sesión personalizada
        transport = Transport(session=session)
        
        # Crear el cliente con el transporte personalizado
        client = Client(wsaa_wsdl, transport=transport)
        
        response = client.service.loginCms(signed_data)
        
        # Create directory if it doesn't exist
        os.makedirs("app/services/tickets", exist_ok=True)
        
        # Save response to file
        now = datetime.datetime.now()
        unique_id = now.strftime("%y%m%d%H%M")
        response_filename = f"app/services/tickets/{unique_id}-loginTicketResponse.xml"
        
        with open(response_filename, "w", encoding="utf-8") as f:
            f.write(response)
        
        return response
    except Exception as e:
        print(f"Error in WSAA call: {e}")
        
        # En entorno de desarrollo, generar una respuesta ficticia en caso de error
        if settings.ENVIRONMENT == "dev":
            print("DEV MODE: Generating mock WSAA response after error")
            # Crear una respuesta XML ficticia con token y sign para pruebas
            now = datetime.datetime.now()
            expiration = now + datetime.timedelta(hours=12)
            mock_response = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<loginTicketResponse version="1.0">
    <header>
        <source>CN=wsaahomo, O=ARCA, C=AR, SERIALNUMBER=CUIT 33693450239</source>
        <destination>SERIALNUMBER=CUIT 20283176789, CN=test</destination>
        <uniqueId>{int(now.timestamp())}</uniqueId>
        <generationTime>{now.isoformat()}</generationTime>
        <expirationTime>{expiration.isoformat()}</expirationTime>
    </header>
    <credentials>
        <token>MOCKTOKEN123456789</token>
        <sign>MOCKSIGN987654321</sign>
    </credentials>
</loginTicketResponse>"""
            
            # Guardar en un archivo para simular el comportamiento normal
            os.makedirs("app/services/tickets", exist_ok=True)
            
            response_filename = f"app/services/tickets/{now.strftime('%y%m%d%H%M')}-loginTicketResponse.xml"
            
            with open(response_filename, "w", encoding="utf-8") as f:
                f.write(mock_response)
            
            return mock_response
            
        raise Exception(f"WSAA Error: {e}")

async def parse_ticket_response(response: str) -> Dict[str, str]:
    """
    Parse the login ticket response XML.
    
    Args:
        response: XML response from WSAA
        
    Returns:
        Dictionary with token, sign, and expiration
    """
    try:
        root = etree.fromstring(response.encode('utf-8'))
        
        # Extract data
        token = root.find(".//token").text
        sign = root.find(".//sign").text
        expiration = root.find(".//expirationTime").text
        generation = root.find(".//generationTime").text
        
        return {
            "token": token,
            "sign": sign,
            "expiration": expiration,
            "generation": generation
        }
    except Exception as e:
        print(f"Error parsing ticket response: {e}")
        return {}

async def check_ticket_validity(service: str, cuit: str, client: Any = None, negocio_id: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    Check if a valid ticket exists for the specified service.
    
    Args:
        service: Service ID (e.g., 'wsfe')
        cuit: CUIT number
        client: Supabase client (optional)
        negocio_id: Business ID (optional)
        
    Returns:
        Dictionary with token and sign or None if no valid ticket exists
    """
    # Check in-memory cache first
    if f"{service}_{cuit}" in ticket_cache:
        ticket = ticket_cache[f"{service}_{cuit}"]
        expiration = datetime.datetime.fromisoformat(ticket["expiration"])
        now = datetime.datetime.now(expiration.tzinfo if expiration.tzinfo else None)
        
        if expiration > now:
            return ticket
            
    # Check in database if client is provided
    if client and negocio_id:
        try:
            config_resp = client.table("configuracion_fiscal").select("wsaa_token, wsaa_sign, wsaa_expiration, wsaa_generation").eq("negocio_id", negocio_id).execute()
            if config_resp.data and config_resp.data[0].get("wsaa_token") and config_resp.data[0].get("wsaa_expiration"):
                config = config_resp.data[0]
                expiration_str = config["wsaa_expiration"]
                # Postgres timestamp with time zone is returned as string
                expiration = datetime.datetime.fromisoformat(expiration_str.replace("Z", "+00:00"))
                now = datetime.datetime.now(datetime.timezone.utc)
                
                if expiration > now:
                    ticket_data = {
                        "token": config["wsaa_token"],
                        "sign": config["wsaa_sign"],
                        "expiration": expiration_str,
                        "generation": config.get("wsaa_generation", "")
                    }
                    ticket_cache[f"{service}_{cuit}"] = ticket_data
                    return ticket_data
        except Exception as e:
            print(f"Error checking ticket in database: {e}")
    
    # Check for saved ticket files (Fallback)
    try:
        ticket_dir = Path("app/services/tickets")
        if not ticket_dir.exists():
            return None
            
        response_files = list(ticket_dir.glob("*-loginTicketResponse.xml"))
        if not response_files:
            return None
            
        # Find the most recent file
        latest_file = max(response_files, key=os.path.getctime)
        
        # Parse the XML
        with open(latest_file, "r", encoding="utf-8") as f:
            response = f.read()
            
        # Parse the ticket
        ticket_data = await parse_ticket_response(response)
        
        # Check expiration
        if not ticket_data or "expiration" not in ticket_data:
            return None
            
        expiration = datetime.datetime.fromisoformat(ticket_data["expiration"])
        now = datetime.datetime.now(expiration.tzinfo if expiration.tzinfo else None)
        
        if expiration > now:
            # Add to cache
            ticket_cache[f"{service}_{cuit}"] = ticket_data
            return ticket_data
            
        return None
    except Exception as e:
        print(f"Error checking ticket validity fallback: {e}")
        return None

async def get_access_ticket(service: str, cert_path: Path, key_path: Path, wsaa_wsdl: str, cuit: str, client: Any = None, negocio_id: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    Get a valid access ticket for the specified ARCA service.
    If no valid ticket exists, create a new one.
    
    Args:
        service: Service ID (e.g., 'wsfe')
        cuit: CUIT number (optional, can be set in the environment)
        client: Supabase client (optional)
        negocio_id: Business ID (optional)
        
    Returns:
        Dictionary with token, sign and cuit or None if there was an error
    """
    # Check if a valid ticket exists
    ticket = await check_ticket_validity(service, cuit, client, negocio_id)
    if ticket:
        # Add CUIT to ticket data
        if cuit:
            ticket["cuit"] = cuit
        elif "ARCA_CUIT" in os.environ:
            ticket["cuit"] = os.environ["ARCA_CUIT"]
        
        return ticket
    
    # Create a new ticket
    try:
        # Create login ticket request
        tra = await create_login_ticket(service)
        
        # Sign the request
        signed_data = await sign_tra(tra, cert_path, key_path)
        if not signed_data:
            raise Exception("Failed to sign TRA. Certificate or private key might be invalid or mismatched.")
        
        # Send to WSAA
        response = await send_ticket_request(signed_data, wsaa_wsdl)
        if not response:
            return None
        
        # Parse response
        ticket_data = await parse_ticket_response(response)
        
        # Add to cache
        ticket_cache[f"{service}_{cuit}"] = ticket_data
        
        # Save to database if client is provided
        if client and negocio_id and "token" in ticket_data and "expiration" in ticket_data:
            try:
                client.table("configuracion_fiscal").update({
                    "wsaa_token": ticket_data["token"],
                    "wsaa_sign": ticket_data["sign"],
                    "wsaa_expiration": ticket_data["expiration"],
                    "wsaa_generation": ticket_data.get("generation")
                }).eq("negocio_id", negocio_id).execute()
            except Exception as db_err:
                print(f"Error saving ticket to database: {db_err}")
        
        # Add CUIT to ticket data
        if cuit:
            ticket_data["cuit"] = cuit
        elif "ARCA_CUIT" in os.environ:
            ticket_data["cuit"] = os.environ["ARCA_CUIT"]
            
        return ticket_data
    except Exception as e:
        print(f"Error getting access ticket: {e}")
        raise e 