import pandas as pd
import re
import difflib
from typing import Dict, List, Optional, Tuple, Any
from io import BytesIO


class ColumnRecognizer:
    """Reconoce y mapea columnas de Excel a campos de productos."""
    
    def __init__(self):
        self.patterns = {
            'nombre': [
                'nombre', 'name', 'producto', 'product', 'descripcion', 'description',
                'articulo', 'item', 'titulo', 'title'
            ],
            'precio': [
                'precio', 'price', 'valor', 'value', 'costo', 'cost', 'importe',
                'amount', 'precio_venta', 'precio_unitario', 'unit_price'
            ],
            'stock': [
                'stock', 'cantidad', 'quantity', 'existencia', 'inventory',
                'disponible', 'available', 'unidades', 'units'
            ],
            'codigo': [
                'codigo', 'code', 'sku', 'barcode', 'codigo_barras', 'id',
                'referencia', 'reference', 'modelo', 'model'
            ],
            'categoria': [
                'categoria', 'category', 'tipo', 'type', 'grupo', 'group',
                'clasificacion', 'classification', 'seccion', 'section'
            ]
        }
    
    def normalize_column_name(self, name: str) -> str:
        """Normaliza el nombre de una columna para comparación."""
        if not name:
            return ""
        
        # Convertir a minúsculas y eliminar caracteres especiales
        normalized = re.sub(r'[^a-zA-Z0-9\s]', '', str(name).lower())
        # Eliminar espacios extra
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        # Reemplazar espacios con guiones bajos
        normalized = normalized.replace(' ', '_')
        
        return normalized
    
    def calculate_confidence(self, column_name: str, pattern: str) -> float:
        """Calcula la confianza de que una columna coincida con un patrón."""
        normalized_column = self.normalize_column_name(column_name)
        normalized_pattern = self.normalize_column_name(pattern)
        
        # Coincidencia exacta
        if normalized_column == normalized_pattern:
            return 100.0
        
        # Usar difflib para calcular similitud
        similarity = difflib.SequenceMatcher(None, normalized_column, normalized_pattern).ratio()
        confidence = similarity * 100
        
        # Bonus por coincidencias parciales
        if normalized_pattern in normalized_column or normalized_column in normalized_pattern:
            confidence = max(confidence, 80.0)
        
        return confidence
    
    def find_best_match(self, column_name: str, field_type: str) -> Tuple[str, float]:
        """Encuentra la mejor coincidencia para una columna."""
        if field_type not in self.patterns:
            return "", 0.0
        
        best_match = ""
        best_confidence = 0.0
        
        for pattern in self.patterns[field_type]:
            confidence = self.calculate_confidence(column_name, pattern)
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = pattern
        
        return best_match, best_confidence
    
    def recognize_columns(self, columns: List[str]) -> Dict[str, Dict[str, Any]]:
        """Reconoce automáticamente las columnas de un DataFrame."""
        recognition_results = {}
        
        for column in columns:
            column_results = {}
            
            for field_type in self.patterns.keys():
                best_match, confidence = self.find_best_match(column, field_type)
                column_results[field_type] = {
                    'confidence': confidence,
                    'pattern': best_match
                }
            
            # Encontrar el mejor match general
            best_field = max(column_results.keys(), 
                           key=lambda x: column_results[x]['confidence'])
            
            recognition_results[column] = {
                'suggested_field': best_field,
                'confidence': column_results[best_field]['confidence'],
                'all_matches': column_results
            }
        
        return recognition_results


class ExcelProcessor:
    """Procesa archivos Excel para importación de productos."""
    
    def __init__(self):
        self.recognizer = ColumnRecognizer()
    
    def read_excel_file(self, file_content: bytes, sheet_name: Optional[str] = None) -> pd.DataFrame:
        """Lee un archivo Excel y retorna un DataFrame."""
        try:
            # Intentar con openpyxl primero (para .xlsx)
            df = pd.read_excel(
                BytesIO(file_content),
                sheet_name=sheet_name,
                engine='openpyxl'
            )
        except Exception as e:
            try:
                # Intentar con xlrd para archivos .xls
                df = pd.read_excel(
                    BytesIO(file_content),
                    sheet_name=sheet_name,
                    engine='xlrd'
                )
            except Exception as e2:
                raise ValueError(f"No se pudo leer el archivo Excel: {str(e)}, {str(e2)}")
        
        return df
    
    def get_sheet_names(self, file_content: bytes) -> List[str]:
        """Obtiene los nombres de las hojas de un archivo Excel."""
        try:
            # Intentar con openpyxl
            excel_file = pd.ExcelFile(BytesIO(file_content), engine='openpyxl')
            return excel_file.sheet_names
        except Exception:
            try:
                # Intentar con xlrd
                excel_file = pd.ExcelFile(BytesIO(file_content), engine='xlrd')
                return excel_file.sheet_names
            except Exception as e:
                raise ValueError(f"No se pudo leer el archivo Excel: {str(e)}")
    
    def clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Limpia y prepara el DataFrame para procesamiento."""
        # Eliminar filas completamente vacías
        df = df.dropna(how='all')
        
        # Eliminar columnas completamente vacías
        df = df.dropna(axis=1, how='all')
        
        # Resetear índices
        df = df.reset_index(drop=True)
        
        # Limpiar nombres de columnas
        df.columns = [str(col).strip() for col in df.columns]
        
        return df
    
    def validate_data_types(self, df: pd.DataFrame, column_mapping: Dict[str, str]) -> Dict[str, List[str]]:
        """Valida los tipos de datos en las columnas mapeadas."""
        errors = {}
        
        for excel_column, field_type in column_mapping.items():
            if excel_column not in df.columns:
                continue
            
            column_errors = []
            
            if field_type == 'precio':
                # Validar que sean números
                for idx, value in df[excel_column].items():
                    if pd.isna(value):
                        continue
                    try:
                        float(str(value).replace(',', '.'))
                    except (ValueError, TypeError):
                        column_errors.append(f"Fila {idx + 2}: '{value}' no es un precio válido")
            
            elif field_type == 'stock':
                # Validar que sean números enteros
                for idx, value in df[excel_column].items():
                    if pd.isna(value):
                        continue
                    try:
                        int(float(str(value)))
                    except (ValueError, TypeError):
                        column_errors.append(f"Fila {idx + 2}: '{value}' no es una cantidad válida")
            
            if column_errors:
                errors[excel_column] = column_errors
        
        return errors
    
    def convert_to_products(self, df: pd.DataFrame, column_mapping: Dict[str, str]) -> List[Dict[str, Any]]:
        """Convierte el DataFrame a una lista de productos."""
        products = []
        
        for idx, row in df.iterrows():
            product = {}
            
            for excel_column, field_type in column_mapping.items():
                if excel_column in df.columns:
                    value = row[excel_column]
                    
                    # Saltar valores nulos
                    if pd.isna(value):
                        continue
                    
                    # Convertir según el tipo de campo
                    if field_type == 'precio':
                        try:
                            product[field_type] = float(str(value).replace(',', '.'))
                        except (ValueError, TypeError):
                            product[field_type] = 0.0
                    
                    elif field_type == 'stock':
                        try:
                            product[field_type] = int(float(str(value)))
                        except (ValueError, TypeError):
                            product[field_type] = 0
                    
                    else:
                        product[field_type] = str(value).strip()
            
            # Solo agregar productos que tengan al menos un nombre
            if product.get('nombre'):
                product['fila_excel'] = idx + 2  # +2 porque Excel empieza en 1 y hay header
                products.append(product)
        
        return products
    
    def process_excel_file(self, file_content: bytes, sheet_name: Optional[str] = None) -> Dict[str, Any]:
        """Procesa completamente un archivo Excel."""
        try:
            # Leer el archivo
            df = self.read_excel_file(file_content, sheet_name)
            
            # Limpiar datos
            df = self.clean_dataframe(df)
            
            if df.empty:
                return {
                    'success': False,
                    'error': 'El archivo Excel está vacío o no contiene datos válidos'
                }
            
            # Reconocer columnas
            column_recognition = self.recognizer.recognize_columns(df.columns.tolist())
            
            # Crear mapeo automático (solo para columnas con alta confianza)
            auto_mapping = {}
            for column, recognition in column_recognition.items():
                if recognition['confidence'] > 70:  # Solo mapear si hay alta confianza
                    auto_mapping[column] = recognition['suggested_field']
            
            return {
                'success': True,
                'data': df.to_dict('records'),
                'columns': df.columns.tolist(),
                'column_recognition': column_recognition,
                'auto_mapping': auto_mapping,
                'total_rows': len(df)
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Error procesando archivo Excel: {str(e)}'
            } 