import pandas as pd
import re
from typing import Dict, List, Optional, Tuple, Any
from fuzzywuzzy import fuzz, process
from io import BytesIO

class ColumnRecognizer:
    """Reconocedor inteligente de columnas de Excel."""
    
    # Mapeo de patrones para reconocer columnas (expandido y mejorado)
    COLUMN_PATTERNS = {
        'nombre': [
            'nombre', 'producto', 'articulo', 'item', 'descripcion_corta',
            'name', 'product', 'article', 'title', 'titulo', 'denominacion',
            'producto_nombre', 'item_name', 'product_name', 'articulo_nombre'
        ],
        'descripcion': [
            'descripcion', 'detalle', 'observaciones', 'notas', 'comentarios',
            'description', 'details', 'notes', 'obs', 'comments', 'info',
            'informacion', 'especificaciones', 'specs', 'caracteristicas'
        ],
        'codigo': [
            'codigo', 'sku', 'cod', 'code', 'barcode', 'codigo_barras',
            'ref', 'referencia', 'id_producto', 'item_code', 'product_code',
            'codigo_producto', 'codigo_interno', 'internal_code', 'upc', 'ean'
        ],
        'precio_venta': [
            'precio', 'precio_venta', 'precio_unitario', 'pvp', 'price',
            'selling_price', 'unit_price', 'precio_publico', 'venta',
            'precio_final', 'precio_cliente', 'customer_price', 'retail_price',
            'precio_retail', 'precio_lista', 'list_price'
        ],
        'precio_compra': [
            'precio_compra', 'costo', 'cost', 'precio_costo', 'compra',
            'buying_price', 'purchase_price', 'costo_unitario', 'wholesale_price',
            'precio_mayorista', 'precio_proveedor', 'supplier_price', 'costo_producto'
        ],
        'stock_actual': [
            'stock', 'cantidad', 'existencia', 'inventory', 'qty', 'quantity',
            'stock_actual', 'disponible', 'available', 'unidades', 'units',
            'inventario', 'existencias', 'stock_disponible', 'current_stock'
        ],
        'stock_minimo': [
            'stock_minimo', 'min_stock', 'minimo', 'stock_min', 'minimum',
            'minimum_stock', 'reorder_point', 'punto_reposicion', 'stock_seguridad',
            'safety_stock', 'nivel_minimo', 'minimum_level'
        ],
        'categoria': [
            'categoria', 'category', 'tipo', 'grupo', 'family', 'familia',
            'clasificacion', 'class', 'seccion', 'section', 'departamento',
            'department', 'linea', 'line', 'rubro', 'area'
        ]
    }
    
    # Palabras clave que indican el tipo de campo
    FIELD_KEYWORDS = {
        'precio_venta': ['precio', 'price', 'venta', 'sell', 'pvp', 'retail'],
        'precio_compra': ['costo', 'cost', 'compra', 'buy', 'wholesale'],
        'stock': ['stock', 'cantidad', 'qty', 'inventory', 'existencia'],
        'codigo': ['codigo', 'code', 'sku', 'ref', 'barcode'],
        'categoria': ['categoria', 'category', 'tipo', 'type', 'grupo', 'group']
    }
    
    def __init__(self, threshold: float = 65.0):
        """
        Inicializa el reconocedor de columnas.
        
        Args:
            threshold: Umbral mínimo de confianza para considerar una coincidencia válida
        """
        self.threshold = threshold
    
    def normalize_column_name(self, column_name: str) -> str:
        """Normaliza el nombre de una columna para mejorar el matching."""
        if not column_name:
            return ""
        
        # Convertir a minúsculas
        normalized = column_name.lower().strip()
        
        # Remover caracteres especiales y espacios extra
        normalized = re.sub(r'[^\w\s]', '', normalized)
        normalized = re.sub(r'\s+', '_', normalized)
        
        # Remover prefijos/sufijos comunes
        normalized = re.sub(r'^(col_|column_|campo_|field_)', '', normalized)
        normalized = re.sub(r'(_col|_column|_campo|_field)$', '', normalized)
        
        return normalized
    
    def calculate_confidence(self, column_name: str, pattern: str) -> float:
        """Calcula la confianza de que una columna coincida con un patrón."""
        normalized_column = self.normalize_column_name(column_name)
        normalized_pattern = self.normalize_column_name(pattern)
        
        # Coincidencia exacta
        if normalized_column == normalized_pattern:
            return 100.0
        
        # Fuzzy matching con múltiples algoritmos
        ratio = fuzz.ratio(normalized_column, normalized_pattern)
        partial_ratio = fuzz.partial_ratio(normalized_column, normalized_pattern)
        token_sort_ratio = fuzz.token_sort_ratio(normalized_column, normalized_pattern)
        token_set_ratio = fuzz.token_set_ratio(normalized_column, normalized_pattern)
        
        # Usar el mejor score de todos los algoritmos
        confidence = max(ratio, partial_ratio, token_sort_ratio, token_set_ratio)
        
        # Bonus por palabras clave contenidas
        if normalized_pattern in normalized_column or normalized_column in normalized_pattern:
            confidence = min(100.0, confidence + 15.0)
        
        # Bonus adicional por palabras clave específicas del campo
        for field, keywords in self.FIELD_KEYWORDS.items():
            if any(keyword in normalized_column for keyword in keywords):
                if any(keyword in normalized_pattern for keyword in keywords):
                    confidence = min(100.0, confidence + 10.0)
                    break
        
        return confidence
    
    def get_best_match_for_field(self, field: str, columns: List[str], used_columns: set) -> Optional[Dict[str, Any]]:
        """Encuentra la mejor coincidencia para un campo específico."""
        patterns = self.COLUMN_PATTERNS.get(field, [])
        best_match = None
        best_confidence = 0.0
        best_column = None
        best_pattern = None
        
        for column in columns:
            if column in used_columns:
                continue
            
            # Calcular confianza para cada patrón
            for pattern in patterns:
                confidence = self.calculate_confidence(column, pattern)
                
                if confidence > best_confidence and confidence >= self.threshold:
                    best_confidence = confidence
                    best_match = pattern
                    best_column = column
                    best_pattern = pattern
        
        if best_column:
            return {
                'column': best_column,
                'confidence': best_confidence / 100.0,  # Normalizar a 0-1
                'pattern_matched': best_pattern
            }
        
        return None
    
    def recognize_columns(self, columns: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Reconoce las columnas del Excel y las mapea a campos del producto.
        
        Args:
            columns: Lista de nombres de columnas del Excel
            
        Returns:
            Diccionario con el mapeo de columnas y su confianza
        """
        mapping = {}
        used_columns = set()
        
        # Orden de prioridad para el reconocimiento
        field_priority = [
            'nombre',           # Más importante
            'precio_venta',     
            'stock_actual',
            'codigo',
            'categoria',
            'precio_compra',
            'descripcion',
            'stock_minimo'      # Menos crítico
        ]
        
        # Procesar campos en orden de prioridad
        for field in field_priority:
            match = self.get_best_match_for_field(field, columns, used_columns)
            if match:
                mapping[field] = match
                used_columns.add(match['column'])
        
        return mapping
    
    def suggest_missing_fields(self, mapping: Dict[str, Dict[str, Any]], columns: List[str]) -> Dict[str, List[str]]:
        """Sugiere posibles campos para columnas no reconocidas."""
        suggestions = {}
        used_columns = {info['column'] for info in mapping.values()}
        unused_columns = [col for col in columns if col not in used_columns]
        
        for column in unused_columns:
            column_suggestions = []
            
            # Buscar similitudes con todos los patrones
            for field, patterns in self.COLUMN_PATTERNS.items():
                if field not in mapping:  # Solo sugerir campos no mapeados
                    for pattern in patterns:
                        confidence = self.calculate_confidence(column, pattern)
                        if confidence >= 50.0:  # Umbral más bajo para sugerencias
                            column_suggestions.append({
                                'field': field,
                                'confidence': confidence / 100.0,
                                'pattern': pattern
                            })
            
            # Ordenar por confianza
            column_suggestions.sort(key=lambda x: x['confidence'], reverse=True)
            suggestions[column] = column_suggestions[:3]  # Top 3 sugerencias
        
        return suggestions

class ExcelProcessor:
    """Procesador de archivos Excel para importación de productos."""
    
    def __init__(self):
        self.recognizer = ColumnRecognizer()
    
    def _detect_file_type(self, file_content: bytes) -> str:
        """Detecta el tipo de archivo basado en su contenido."""
        try:
            # Verificar si es un archivo Excel por magic bytes
            if file_content.startswith(b'PK\x03\x04'):  # ZIP signature (xlsx)
                return 'excel'
            elif file_content.startswith(b'\xd0\xcf\x11\xe0'):  # OLE signature (xls)
                return 'excel'
            elif file_content.startswith(b'\x09\x08'):  # Algunos archivos XLS
                return 'excel'
            
            # Intentar decodificar como texto para verificar si es CSV
            try:
                text_content = file_content.decode('utf-8')
                # Si contiene comas y parece texto plano, probablemente es CSV
                if ',' in text_content and len(text_content.splitlines()) > 1:
                    return 'csv'
            except UnicodeDecodeError:
                try:
                    # Intentar con encoding latin-1
                    text_content = file_content.decode('latin-1')
                    if ',' in text_content and len(text_content.splitlines()) > 1:
                        return 'csv'
                except UnicodeDecodeError:
                    pass
            
            # Si no se puede determinar, asumir Excel por defecto
            return 'excel'
            
        except Exception:
            return 'excel'

    def validate_excel_file(self, file_content: bytes) -> Tuple[bool, str]:
        """Valida que el archivo sea un Excel o CSV válido."""
        try:
            file_type = self._detect_file_type(file_content)
            
            if file_type == 'csv':
                try:
                    # Intentar múltiples encodings para CSV
                    for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                        try:
                            df = pd.read_csv(BytesIO(file_content), encoding=encoding)
                            break
                        except UnicodeDecodeError:
                            continue
                    else:
                        return False, "No se pudo leer el archivo CSV con ningún encoding"
                    
                    if df.empty:
                        return False, "El archivo CSV está vacío"
                    
                    if len(df.columns) < 2:
                        return False, "El archivo debe tener al menos 2 columnas"
                    
                    return True, "Archivo CSV válido"
                    
                except Exception as csv_error:
                    return False, f"Error al leer el archivo CSV: {str(csv_error)}"
            
            else:  # Excel
                try:
                    # Intentar leer como Excel con diferentes engines
                    engines = ['openpyxl', 'xlrd']
                    df = None
                    
                    for engine in engines:
                        try:
                            df = pd.read_excel(BytesIO(file_content), nrows=1, engine=engine)
                            break
                        except Exception:
                            continue
                    
                    if df is None:
                        return False, "No se pudo leer el archivo Excel con ningún engine"
                    
                    if df.empty:
                        return False, "El archivo Excel está vacío"
                    
                    if len(df.columns) < 2:
                        return False, "El archivo debe tener al menos 2 columnas"
                    
                    return True, "Archivo Excel válido"
                    
                except Exception as excel_error:
                    return False, f"Error al leer el archivo Excel: {str(excel_error)}"
            
        except Exception as e:
            return False, f"Error al validar el archivo: {str(e)}"
    
    def process_excel(self, file_content: bytes, sheet_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Procesa un archivo Excel o CSV y extrae los datos de productos.
        
        Args:
            file_content: Contenido del archivo en bytes
            sheet_name: Nombre de la hoja a procesar (solo para Excel)
            
        Returns:
            Diccionario con los datos procesados
        """
        try:
            file_type = self._detect_file_type(file_content)
            
            if file_type == 'csv':
                # Leer como CSV con múltiples encodings
                df = None
                for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                    try:
                        df = pd.read_csv(BytesIO(file_content), encoding=encoding)
                        break
                    except UnicodeDecodeError:
                        continue
                
                if df is None:
                    raise ValueError("No se pudo leer el archivo CSV con ningún encoding")
                    
            else:  # Excel
                # Leer como Excel con diferentes engines
                df = None
                engines = ['openpyxl', 'xlrd']
                
                for engine in engines:
                    try:
                        if sheet_name:
                            df = pd.read_excel(BytesIO(file_content), sheet_name=sheet_name, engine=engine)
                        else:
                            df = pd.read_excel(BytesIO(file_content), engine=engine)
                        break
                    except Exception as e:
                        continue
                
                if df is None:
                    raise ValueError("No se pudo leer el archivo Excel. Verifica que el formato sea correcto (.xlsx, .xls)")
            
            # Validar que no esté vacío
            if df.empty:
                raise ValueError("El archivo está vacío")
            
            # Limpiar nombres de columnas
            df.columns = [str(col).strip() for col in df.columns]
            
            # Reconocer columnas
            column_mapping = self.recognizer.recognize_columns(df.columns.tolist())
            
            # Obtener sugerencias para columnas no reconocidas
            suggestions = self.recognizer.suggest_missing_fields(column_mapping, df.columns.tolist())
            
            # Procesar filas
            productos_data = []
            errores_generales = []
            
            for index, row in df.iterrows():
                try:
                    producto_data = self._process_row(row, column_mapping, index + 2)  # +2 porque empieza en 1 y tiene header
                    productos_data.append(producto_data)
                except Exception as e:
                    errores_generales.append(f"Error en fila {index + 2}: {str(e)}")
            
            return {
                'total_filas': len(df),
                'productos_data': productos_data,
                'column_mapping': column_mapping,
                'column_suggestions': suggestions,
                'errores_generales': errores_generales,
                'columnas_originales': df.columns.tolist()
            }
            
        except Exception as e:
            raise ValueError(f"Error al procesar el archivo: {str(e)}")
    
    def _process_row(self, row: pd.Series, column_mapping: Dict[str, Dict[str, Any]], fila_excel: int) -> Dict[str, Any]:
        """Procesa una fila individual del Excel."""
        producto_data = {
            'fila_excel': fila_excel,
            'datos_originales': row.to_dict(),
            'errores': [],
            'confianzas': {}
        }
        
        # Mapear cada campo
        for field, mapping_info in column_mapping.items():
            column_name = mapping_info['column']
            confidence = mapping_info['confidence']
            
            value = row.get(column_name)
            
            # Limpiar y convertir el valor
            processed_value = self._clean_and_convert_value(value, field)
            
            if processed_value is not None:
                if field == 'categoria':
                    producto_data['categoria_nombre'] = processed_value
                else:
                    producto_data[field] = processed_value
                
                producto_data['confianzas'][f'confianza_{field}'] = confidence
        
        # Validaciones básicas
        self._validate_producto_data(producto_data)
        
        return producto_data
    
    def _clean_and_convert_value(self, value: Any, field: str) -> Any:
        """Limpia y convierte un valor según el tipo de campo."""
        if pd.isna(value) or value == '' or value is None:
            return None
        
        try:
            if field in ['precio_venta', 'precio_compra']:
                # Limpiar y convertir precios
                if isinstance(value, str):
                    # Remover símbolos de moneda y espacios
                    cleaned = re.sub(r'[^\d.,]', '', str(value))
                    cleaned = cleaned.replace(',', '.')
                    return float(cleaned) if cleaned else None
                return float(value)
            
            elif field in ['stock_actual', 'stock_minimo']:
                # Convertir a entero
                if isinstance(value, str):
                    cleaned = re.sub(r'[^\d]', '', str(value))
                    return int(cleaned) if cleaned else None
                return int(float(value))  # Por si viene como float
            
            elif field in ['nombre', 'descripcion', 'codigo', 'categoria']:
                # Limpiar texto
                return str(value).strip() if value else None
            
            else:
                return str(value).strip() if value else None
                
        except (ValueError, TypeError):
            return None
    
    def _validate_producto_data(self, producto_data: Dict[str, Any]) -> None:
        """Valida los datos de un producto y agrega errores si es necesario."""
        errores = producto_data['errores']
        
        # Validar campos obligatorios
        if not producto_data.get('nombre'):
            errores.append("El nombre del producto es obligatorio")
        
        # Validar precios
        precio_venta = producto_data.get('precio_venta')
        if precio_venta is not None and precio_venta <= 0:
            errores.append("El precio de venta debe ser mayor a 0")
        
        precio_compra = producto_data.get('precio_compra')
        if precio_compra is not None and precio_compra <= 0:
            errores.append("El precio de compra debe ser mayor a 0")
        
        # Validar stock
        stock_actual = producto_data.get('stock_actual')
        if stock_actual is not None and stock_actual < 0:
            errores.append("El stock actual no puede ser negativo")
        
        stock_minimo = producto_data.get('stock_minimo')
        if stock_minimo is not None and stock_minimo < 0:
            errores.append("El stock mínimo no puede ser negativo")
        
        # Validar código (si existe, debe ser único)
        codigo = producto_data.get('codigo')
        if codigo and len(codigo) > 50:
            errores.append("El código no puede tener más de 50 caracteres")
    
    def get_sheet_names(self, file_content: bytes) -> List[str]:
        """Obtiene los nombres de las hojas del archivo Excel o retorna ['Sheet1'] para CSV."""
        try:
            file_type = self._detect_file_type(file_content)
            
            if file_type == 'csv':
                # Es un archivo CSV, retornar una hoja ficticia
                return ['Sheet1']
            else:
                # Es un archivo Excel, intentar con diferentes engines
                engines = ['openpyxl', 'xlrd']
                
                for engine in engines:
                    try:
                        excel_file = pd.ExcelFile(BytesIO(file_content), engine=engine)
                        return excel_file.sheet_names
                    except Exception:
                        continue
                
                # Si no se puede leer con ningún engine, retornar hoja por defecto
                return ['Sheet1']
                
        except Exception as e:
            raise ValueError(f"Error al leer las hojas del archivo: {str(e)}") 