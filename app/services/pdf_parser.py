import io
import os
import base64
import logging
import json
import time
from typing import List, Dict, Any, Optional
from pdf2image import convert_from_bytes
from pydantic import BaseModel, Field
from openai import OpenAI, RateLimitError
from decouple import config
from tenacity import retry, stop_after_attempt, wait_random_exponential

# Configure logging
logger = logging.getLogger(__name__)

# Initialize OpenAI client
# Ensure OPENAI_API_KEY is set in your environment variables or .env file
client = OpenAI(api_key=config("OPENAI_API_KEY", default=None))

# --- Pydantic Models for Structured Output ---

class ProductItem(BaseModel):
    codigo: str = Field(..., description="El código del producto, ej: '12345' o 'COD: 12345'")
    descripcion: str = Field(..., description="La descripción completa del producto")
    precio_bruto: str = Field(..., description="El precio exacto como aparece en la imagen, incluyendo símbolos y texto extra, ej: '$ 1.200 + iva'")

class CatalogPage(BaseModel):
    products: List[ProductItem] = Field(default_factory=list, description="Lista de productos encontrados en la página")

# --- Helper Functions ---

def limpiar_precio(precio_str: str) -> float:
    """
    Limpia el string de precio bruto y lo convierte a float.
    Maneja símbolos de moneda, texto extra (+ iva) y formatos de miles/decimales.
    
    Args:
        precio_str (str): El precio bruto, ej: "$ 1.200,50 + iva"
        
    Returns:
        float: El valor numérico del precio. Retorna 0.0 si falla.
    """
    if not precio_str:
        return 0.0
    
    # 1. Eliminar texto no numérico común (mantener dígitos, puntos, comas, signos menos)
    # Convertimos a minúsculas para eliminar 'iva', 'usd', etc.
    s = precio_str.lower()
    
    # Eliminar símbolos y texto conocido
    replacements = ['$', 'usd', 'eur', '+', 'iva', 'mas', 'impuestos', 'neto']
    for r in replacements:
        s = s.replace(r, '')
        
    # Eliminar cualquier otro caracter que no sea dígito, punto, coma o espacio
    # (Mantenemos espacios para separar posibles números pegados, aunque idealmente ya limpiamos)
    s = "".join([c for c in s if c.isdigit() or c in ['.', ',', '-']])
    
    # Limpiar espacios extra
    s = s.strip()
    
    if not s:
        return 0.0

    # Lógica de detección de formato (Miles vs Decimales)
    # Asumimos formatos comunes en LatAm/Europa: 1.200,50 (Punto miles, Coma decimal)
    # O formato US: 1,200.50 (Coma miles, Punto decimal)
    
    try:
        if ',' in s and '.' in s:
            if s.find(',') > s.find('.'):
                # Formato 1.200,50 -> Eliminar punto, reemplazar coma por punto
                s = s.replace('.', '').replace(',', '.')
            else:
                # Formato 1,200.50 -> Eliminar coma
                s = s.replace(',', '')
        elif ',' in s:
            # Solo comas: 1200,50 o 1,200 (ambiguo, pero en precios suele ser decimal si hay dos dígitos después, o miles si son 3)
            # Estrategia segura para precios de catálogos locales: Asumir coma es decimal si parece decimal
            # O si es formato 1,000 -> es 1000.
            # Si el string es "1,200", es 1200. Si es "1,50", es 1.5.
            # Ante la duda en LatAm, coma suele ser decimal.
            s = s.replace(',', '.')
        
        # Si solo hay puntos "1.200", suele ser miles. "10.50" podría ser decimal.
        # En muchos catálogos de ferretería/pymes, 1.200 es mil doscientos.
        # Vamos a asumir que si tiene puntos y NO comas, eliminamos los puntos (miles).
        # EXCEPCIÓN: Si tiene un solo punto y menos de 3 decimales, podría ser formato US.
        # Pero para consistencia con "1.200,50", asumiremos punto = miles.
        elif '.' in s:
             # Contar puntos
             if s.count('.') > 1:
                 # 1.000.000 -> Miles
                 s = s.replace('.', '')
             else:
                 # Un solo punto. 1.200 vs 10.50
                 # Si los decimales son exactamente 3, es probable que sea miles (1.200).
                 parts = s.split('.')
                 if len(parts[1]) == 3:
                     s = s.replace('.', '')
                 else:
                     # Asumimos decimal (10.50) - Riesgoso pero necesario decisión
                     pass 
        
        return float(s)
    except ValueError:
        logger.warning(f"No se pudo convertir el precio: {precio_str} -> {s}")
        return 0.0

def encode_image(image_bytes: bytes) -> str:
    """Codifica bytes de imagen a base64 string."""
    return base64.b64encode(image_bytes).decode('utf-8')

@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(5))
def extract_products_from_image(image_bytes: bytes, page_num: int) -> List[Dict[str, Any]]:
    """
    Envía la imagen al LLM para extraer productos.
    Retries on failure (especially rate limits).
    """
    base64_image = encode_image(image_bytes)
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Cost-effective model
            messages=[
                {
                    "role": "system",
                    "content": "Eres un asistente experto en digitalización de catálogos de productos. Tu tarea es extraer información estructurada de imágenes de catálogos."
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Analiza esta imagen del catálogo y extrae todos los productos listados. Para cada producto, necesito el código, la descripción y el precio bruto exacto (tal cual se ve). Devuelve un JSON estructurado."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            response_format={ "type": "json_object" }, # Force JSON mode
            temperature=0.1, # Low temperature for deterministic results
        )
        
        content = response.choices[0].message.content
        if not content:
            return []
            
        # Parse JSON response using Pydantic for validation
        # The LLM might wrap it in a root key like "products" or just return the list.
        # We'll try to parse it into our CatalogPage model.
        
        # Sometimes LLM returns just the list, sometimes { "products": [...] }
        # We instructed "JSON Structured", usually follows schema if provided in tools, 
        # but here we are using json_mode. Let's try to parse generic JSON first.
        data = json.loads(content)
        
        products_list = []
        if isinstance(data, list):
            products_list = data
        elif isinstance(data, dict):
            # Look for common keys
            for key in ['products', 'items', 'productos', 'catalog']:
                if key in data and isinstance(data[key], list):
                    products_list = data[key]
                    break
            if not products_list and 'products' not in data:
                 # Fallback: maybe the dict itself is a single product? Unlikely for a catalog page.
                 pass

        # Validate and convert
        valid_products = []
        for p in products_list:
            try:
                # Map keys if they are slightly different (LLM can be unpredictable without strict schema enforcement via tools)
                # But gpt-4o-mini is good at following instructions.
                # Let's normalize keys just in case
                normalized_p = {}
                for k, v in p.items():
                    k_lower = k.lower()
                    if 'cod' in k_lower: normalized_p['codigo'] = str(v)
                    elif 'desc' in k_lower: normalized_p['descripcion'] = str(v)
                    elif 'prec' in k_lower: normalized_p['precio_bruto'] = str(v)
                
                if 'codigo' in normalized_p and 'descripcion' in normalized_p and 'precio_bruto' in normalized_p:
                    item = ProductItem(**normalized_p)
                    
                    # Post-process
                    price_val = limpiar_precio(item.precio_bruto)
                    
                    valid_products.append({
                        "code": item.codigo,
                        "description": item.descripcion,
                        "raw_price": item.precio_bruto,
                        "price_value": price_val,
                        "page": page_num
                    })
            except Exception as e:
                logger.warning(f"Error validating product item: {p} - {e}")
                continue
                
        return valid_products

    except Exception as e:
        logger.error(f"Error calling LLM for page {page_num}: {e}")
        return []

# --- Main Function ---

def parse_pdf_catalog(file_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parses a PDF catalog file using Multimodal LLM (GPT-4o-mini).
    
    1. Converts PDF pages to Images.
    2. Sends each image to LLM to extract structured data.
    3. Post-processes prices.
    """
    all_products = []
    
    try:
        # Convert PDF to images
        # fmt='jpeg' for smaller payload size than png
        logger.info("Converting PDF to images...")
        
        # Check for POPPLER env var (user specific config)
        # Use decouple config to ensure .env is read
        poppler_path = config("POPPLER", default=None)
        
        logger.info(f"Using Poppler path: {poppler_path}")
        
        images = convert_from_bytes(file_bytes, fmt='jpeg', poppler_path=poppler_path)
        logger.info(f"Converted {len(images)} pages.")
        
        for i, image in enumerate(images):
            page_num = i + 1
            logger.info(f"Processing page {page_num} with LLM...")
            
            # Convert PIL Image to bytes
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='JPEG')
            img_bytes = img_byte_arr.getvalue()
            
            products = extract_products_from_image(img_bytes, page_num)
            all_products.extend(products)
            
            logger.info(f"Extracted {len(products)} products from page {page_num}.")
            
            # Add a small delay to avoid hitting rate limits too aggressively
            time.sleep(1)
            
    except Exception as e:
        logger.error(f"Error parsing PDF catalog: {str(e)}")
        # Re-raise or return empty? User expects exception on failure usually, 
        # but if partial success, maybe return what we have? 
        # The original code raised exception. Let's keep it consistent.
        raise e
        
    return all_products
