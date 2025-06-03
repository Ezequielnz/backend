#!/usr/bin/env python3
"""
Script para crear un archivo Excel de ejemplo para probar el sistema de importación.
"""

import pandas as pd
from datetime import datetime

def crear_excel_ejemplo():
    """Crea un archivo Excel de ejemplo con productos."""
    
    # Datos de ejemplo
    productos = [
        {
            'Nombre': 'Laptop HP Pavilion',
            'Descripcion': 'Laptop HP Pavilion 15 pulgadas, 8GB RAM, 256GB SSD',
            'Codigo': 'LAP001',
            'Precio Venta': 1200.00,
            'Precio Compra': 1000.00,
            'Stock Actual': 10,
            'Stock Minimo': 2,
            'Categoria': 'Electrónicos'
        },
        {
            'Nombre': 'Mouse Inalámbrico Logitech',
            'Descripcion': 'Mouse inalámbrico Logitech MX Master 3',
            'Codigo': 'MOU001',
            'Precio Venta': 25.99,
            'Precio Compra': 18.00,
            'Stock Actual': 50,
            'Stock Minimo': 10,
            'Categoria': 'Accesorios'
        },
        {
            'Nombre': 'Teclado Mecánico',
            'Descripcion': 'Teclado mecánico RGB con switches azules',
            'Codigo': 'TEC001',
            'Precio Venta': 89.99,
            'Precio Compra': 65.00,
            'Stock Actual': 25,
            'Stock Minimo': 5,
            'Categoria': 'Accesorios'
        },
        {
            'Nombre': 'Monitor 24 pulgadas',
            'Descripcion': 'Monitor LED 24 pulgadas Full HD',
            'Codigo': 'MON001',
            'Precio Venta': 199.99,
            'Precio Compra': 150.00,
            'Stock Actual': 15,
            'Stock Minimo': 3,
            'Categoria': 'Electrónicos'
        },
        {
            'Nombre': 'Silla Ergonómica',
            'Descripcion': 'Silla de oficina ergonómica con soporte lumbar',
            'Codigo': 'SIL001',
            'Precio Venta': 299.99,
            'Precio Compra': 220.00,
            'Stock Actual': 8,
            'Stock Minimo': 2,
            'Categoria': 'Muebles'
        }
    ]
    
    # Crear DataFrame
    df = pd.DataFrame(productos)
    
    # Guardar como Excel
    filename = f'ejemplo_productos_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    df.to_excel(filename, index=False, engine='openpyxl')
    
    print(f"✅ Archivo Excel creado: {filename}")
    print(f"📊 Productos incluidos: {len(productos)}")
    print(f"📋 Columnas: {', '.join(df.columns)}")
    
    return filename

if __name__ == "__main__":
    crear_excel_ejemplo() 