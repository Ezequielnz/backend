import io
import os
import base64
import logging
import json
import time
import pandas as pd
from io import BytesIO
from typing import List, Dict, Any, Optional
from pdf2image import convert_from_bytes
from PIL import Image
from openai import OpenAI
from decouple import config
from tenacity import retry, stop_after_attempt, wait_random_exponential

logger = logging.getLogger(__name__)
client = OpenAI(api_key=config("OPENAI_API_KEY", default=None))

class AiImportParser:
    """Servicio unificado para extraer y mapear datos desde Excel o PDF usando OpenAI."""
    
    def __init__(self):
        self.model = "gpt-4o-mini"
        
        self.entity_schemas = {
            "productos": {
                "fields": {
                    "codigo": "Código único del producto (string). Si no hay, dejar vacío.",
                    "nombre": "Nombre principal del producto (string)",
                    "descripcion": "Descripción adicional (string)",
                    "precio": "Precio numérico final (float). Importante limpiar símbolos monetarios.",
                    "stock": "Cantidad en stock (int). Por defecto 0.",
                    "unidades": "Unidad de medida (kg, lt, u, etc.)",
                    "categoria": "Categoría o rubro (string)"
                },
                "required": ["nombre", "precio"]
            },
            "clientes": {
                "fields": {
                    "razon_social": "Nombre completo o Razón Social (string)",
                    "documento_numero": "CUIT, CUIL o DNI numérico (string)",
                    "documento_tipo": "Tipo de documento (CUIT, DNI, etc.)",
                    "email": "Correo electrónico",
                    "telefono": "Teléfono o celular",
                    "direccion": "Domicilio",
                    "condicion_iva": "Responsable Inscripto, Monotributista, etc."
                },
                "required": ["razon_social"]
            },
            "proveedores": {
                "fields": {
                    "razon_social": "Nombre completo o Razón Social (string)",
                    "documento_numero": "CUIT, CUIL o DNI numérico (string)",
                    "documento_tipo": "Tipo de documento (CUIT, DNI, etc.)",
                    "email": "Correo electrónico",
                    "telefono": "Teléfono o celular",
                    "direccion": "Domicilio",
                    "condicion_iva": "Responsable Inscripto, Monotributista, etc."
                },
                "required": ["razon_social"]
            }
        }

    # --- EXCEL LOGIC ---
    
    def parse_excel(self, file_content: bytes, entity_type: str) -> Dict[str, Any]:
        """Procesa un archivo Excel, usando IA para mapear las columnas."""
        try:
            # Leer excel
            try:
                df = pd.read_excel(BytesIO(file_content), engine='openpyxl')
            except:
                df = pd.read_excel(BytesIO(file_content), engine='xlrd')
                
            df = df.dropna(how='all').dropna(axis=1, how='all')
            df.columns = [str(c).strip() for c in df.columns]
            
            if df.empty:
                raise ValueError("El archivo Excel está vacío.")
                
            # Extraer las cabeceras y las primeras 5 filas de ejemplo
            sample_df = df.head(5)
            sample_json = sample_df.to_json(orient='records', force_ascii=False)
            
            schema = self.entity_schemas.get(entity_type, self.entity_schemas["productos"])
            
            # Pedir a OpenAI que mapee las columnas
            mapping_prompt = f"""
Eres un asistente experto en bases de datos.
Tengo un archivo Excel que representa una lista de {entity_type}.
Estas son las columnas originales y 5 filas de ejemplo en formato JSON:
{sample_json}

Necesito que analices los nombres de las columnas Y los datos de ejemplo, y mapees cada columna original al campo del sistema correspondiente.
Los campos del sistema disponibles son:
{json.dumps(schema['fields'], indent=2, ensure_ascii=False)}

Devuelve EXCLUSIVAMENTE un objeto JSON donde la clave es el nombre exacto de la columna original del Excel, y el valor es el nombre del campo del sistema al que corresponde.
Solo incluye las columnas que tengan un mapeo claro. Si una columna es basura o irrelevante, no la incluyas.
"""

            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": mapping_prompt}],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            
            content = response.choices[0].message.content
            if not content:
                content = "{}"
            column_mapping = json.loads(content)
            
            # Aplicar mapeo y normalizar datos
            mapped_data = []
            for _, row in df.iterrows():
                item = {}
                is_empty_row = True
                for excel_col, system_col in column_mapping.items():
                    if excel_col in df.columns:
                        val = row[excel_col]
                        if pd.notna(val):
                            is_empty_row = False
                            # Parseo básico según tipo
                            if system_col in ['precio', 'stock']:
                                try:
                                    if system_col == 'precio':
                                        val_str = str(val).replace('$', '').replace(' ', '')
                                        if ',' in val_str and '.' in val_str:
                                            val_str = val_str.replace('.', '').replace(',', '.')
                                        elif ',' in val_str:
                                            val_str = val_str.replace(',', '.')
                                        item[system_col] = float(val_str)
                                    else:
                                        item[system_col] = int(float(val))
                                except:
                                    item[system_col] = 0
                            else:
                                item[system_col] = str(val).strip()
                
                if not is_empty_row:
                    # Validar requirimientos mínimos (ej: tiene que tener nombre/razon_social)
                    has_required = any(req in item and item[req] for req in schema['required'])
                    if has_required:
                        mapped_data.append(item)
                        
            return {
                "success": True,
                "data_preview": mapped_data,
                "mapeo_automatico": column_mapping,
                "total_filas": len(mapped_data),
                "source": "excel"
            }
            
        except Exception as e:
            logger.error(f"Error procesando Excel con IA: {e}")
            raise e

    # --- PDF LOGIC ---
    
    def _encode_image(self, image: Image.Image) -> str:
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='JPEG', quality=85)
        return base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')

    def _resize_image_for_llm(self, image: Image.Image, max_size: int = 1024) -> Image.Image:
        width, height = image.size
        if width <= max_size and height <= max_size:
            return image
        if width > height:
            new_width = max_size
            new_height = int(height * (max_size / width))
        else:
            new_height = max_size
            new_width = int(width * (max_size / height))
        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    @retry(wait=wait_random_exponential(min=1, max=10), stop=stop_after_attempt(3))
    def _extract_from_image(self, base64_image: str, entity_type: str) -> List[Dict[str, Any]]:
        schema = self.entity_schemas.get(entity_type, self.entity_schemas["productos"])
        
        prompt = f"""
Extrae la información de todos los {entity_type} listados en esta imagen.
Devuelve un JSON estrictamente estructurado con la clave "items", que contenga un arreglo de objetos.
Cada objeto debe tener estos campos exactos si están disponibles (si no, omitirlos o dejarlos vacíos):
{json.dumps(schema['fields'], indent=2, ensure_ascii=False)}

Asegúrate de limpiar los precios de símbolos y dejarlos como números, y extraer todo el texto posible para el nombre o razón social.
"""
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Eres un asistente de digitalización de documentos. Solo respondes en JSON puro."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "high"}}
                    ]
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        content = response.choices[0].message.content
        if not content:
            content = "{}"
        data = json.loads(content)
        items = data.get("items", [])
        if not items and isinstance(data, list):
            items = data
            
        # Post-procesamiento
        valid_items = []
        for item in items:
            has_required = any(req in item and item[req] for req in schema['required'])
            if has_required:
                valid_items.append(item)
                
        return valid_items

    def parse_pdf(self, file_content: bytes, entity_type: str) -> Dict[str, Any]:
        """Procesa un PDF convirtiéndolo a imágenes y usando GPT-4 Vision."""
        try:
            poppler_path = config("POPPLER", default=None)
            images = convert_from_bytes(file_content, fmt='jpeg', dpi=150, poppler_path=poppler_path)
            
            all_data = []
            for i, image in enumerate(images):
                opt_image = self._resize_image_for_llm(image)
                b64_img = self._encode_image(opt_image)
                items = self._extract_from_image(b64_img, entity_type)
                all_data.extend(items)
                time.sleep(1) # Rate limit
                
            return {
                "success": True,
                "data_preview": all_data,
                "mapeo_automatico": {f:f for f in self.entity_schemas[entity_type]['fields'].keys()},
                "total_filas": len(all_data),
                "source": "pdf"
            }
        except Exception as e:
            logger.error(f"Error procesando PDF con IA: {e}")
            raise e
