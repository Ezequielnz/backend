import pytest
import pandas as pd
import io
from app.services.importacion_excel import ColumnRecognizer, ExcelProcessor

def create_excel_bytes(data: dict) -> bytes:
    """Helper to create Excel file bytes in memory."""
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

def test_column_recognizer_perfect_match():
    recognizer = ColumnRecognizer()
    columns = ['nombre', 'precio', 'stock', 'codigo', 'categoria']
    results = recognizer.recognize_columns(columns)
    
    assert results['nombre']['suggested_field'] == 'nombre'
    assert results['precio']['suggested_field'] == 'precio'
    assert results['stock']['suggested_field'] == 'stock'
    assert results['codigo']['suggested_field'] == 'codigo'
    assert results['categoria']['suggested_field'] == 'categoria'
    
    for col in columns:
        assert results[col]['confidence'] == 100.0

def test_column_recognizer_imperfect_match():
    recognizer = ColumnRecognizer()
    columns = ['Nomb re', 'Precio Lista ($)', 'Cantidad Actual ', 'SKU-123', 'Grupito']
    results = recognizer.recognize_columns(columns)
    
    # Nomb re -> nombre
    assert results['Nomb re']['suggested_field'] == 'nombre'
    assert results['Nomb re']['confidence'] >= 80.0
    
    # Precio Lista ($) -> precio
    assert results['Precio Lista ($)']['suggested_field'] == 'precio'
    assert results['Precio Lista ($)']['confidence'] >= 80.0
    
    # Cantidad Actual -> stock (cantidad)
    assert results['Cantidad Actual ']['suggested_field'] == 'stock'
    assert results['Cantidad Actual ']['confidence'] >= 80.0
    
    # SKU-123 -> codigo (sku)
    assert results['SKU-123']['suggested_field'] == 'codigo'
    assert results['SKU-123']['confidence'] >= 80.0

def test_column_recognizer_customers_suppliers():
    recognizer = ColumnRecognizer()
    columns = [
        'Razón Social', 'CUIT/CUIL', 'Correo Electrónico', 'WhatsApp', 
        'Domicilio', 'Situación IVA'
    ]
    results = recognizer.recognize_columns(columns)
    
    assert results['Razón Social']['suggested_field'] == 'razon_social'
    assert results['CUIT/CUIL']['suggested_field'] == 'documento_numero'
    assert results['Correo Electrónico']['suggested_field'] == 'email'
    assert results['WhatsApp']['suggested_field'] == 'telefono'
    assert results['Domicilio']['suggested_field'] == 'direccion'
    assert results['Situación IVA']['suggested_field'] == 'condicion_iva'

def test_excel_processor_clean_data():
    processor = ExcelProcessor()
    
    # Data with empty rows and columns
    data = {
        'Nombre': ['Producto 1', None, 'Producto 2'],
        'Empty Col': [None, None, None],
        'Precio': [10.5, None, 20.0]
    }
    
    df = pd.DataFrame(data)
    cleaned_df = processor.clean_dataframe(df)
    
    # Should drop the entirely empty column
    assert 'Empty Col' not in cleaned_df.columns
    # Should drop the entirely empty row (index 1)
    assert len(cleaned_df) == 2
    assert cleaned_df.iloc[1]['Nombre'] == 'Producto 2'

def test_excel_processor_validate_data_types():
    processor = ExcelProcessor()
    
    data = {
        'nombre': ['Prod A', 'Prod B', 'Prod C'],
        'precio': ['10.5', 'Gratis', '20,50'],
        'stock': ['10', 'No hay', '5.5']
    }
    df = pd.DataFrame(data)
    
    mapping = {'nombre': 'nombre', 'precio': 'precio', 'stock': 'stock'}
    errors = processor.validate_data_types(df, mapping)
    
    assert 'precio' in errors
    assert len(errors['precio']) == 1
    assert "Fila 3" in errors['precio'][0]  # Prod B is row 3 in Excel (idx 1 + 2)
    
    assert 'stock' in errors
    assert len(errors['stock']) == 1
    assert "Fila 3" in errors['stock'][0]  # Prod B

def test_excel_processor_convert_to_products():
    processor = ExcelProcessor()
    
    data = {
        'Nombre Col': ['Prod A', 'Prod B'],
        'Precio Col': ['10.5', '20,50'],
        'Stock Col': ['10', '15']
    }
    df = pd.DataFrame(data)
    
    mapping = {'Nombre Col': 'nombre', 'Precio Col': 'precio', 'Stock Col': 'stock'}
    products = processor.convert_to_products(df, mapping)
    
    assert len(products) == 2
    assert products[0]['nombre'] == 'Prod A'
    assert products[0]['precio'] == 10.5
    assert products[0]['stock'] == 10
    
    assert products[1]['nombre'] == 'Prod B'
    assert products[1]['precio'] == 20.5
    assert products[1]['stock'] == 15

def test_process_excel_file_end_to_end():
    processor = ExcelProcessor()
    
    data = {
        'Nombre': ['Test A', 'Test B'],
        'Precio': [100, 200],
        'Stock': [10, 20],
        'SKU': ['SKU1', 'SKU2']
    }
    
    excel_bytes = create_excel_bytes(data)
    
    result = processor.process_excel_file(excel_bytes)
    
    if not result['success']:
        print("ERROR:", result.get('error'))
    assert result['success'] is True
    assert len(result['columns']) == 4
    
    # Check recognition
    assert result['column_recognition']['Nombre']['suggested_field'] == 'nombre'
    assert result['column_recognition']['Precio']['suggested_field'] == 'precio'
    
    # Check sample data
    assert len(result['data']) == 2
    assert result['data'][0]['Nombre'] == 'Test A'

def test_process_excel_file_invalid_file():
    processor = ExcelProcessor()
    
    invalid_bytes = b"This is not an excel file"
    
    result = processor.process_excel_file(invalid_bytes)
    
    assert result['success'] is False
    assert "error" in result
