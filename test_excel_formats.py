#!/usr/bin/env python3
"""
Script para probar diferentes formatos de Excel y CSV.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from app.services.importacion_excel import ExcelProcessor

def test_file_detection():
    """Prueba la detección de diferentes tipos de archivo."""
    
    print("🧪 PROBANDO DETECCIÓN DE FORMATOS DE ARCHIVO")
    print("=" * 60)
    
    processor = ExcelProcessor()
    
    # Probar archivo CSV
    try:
        with open('test_productos.csv', 'rb') as f:
            csv_content = f.read()
        
        print("\n📄 ARCHIVO CSV:")
        print(f"   Tamaño: {len(csv_content)} bytes")
        
        # Detectar tipo
        file_type = processor._detect_file_type(csv_content)
        print(f"   Tipo detectado: {file_type}")
        
        # Validar
        is_valid, message = processor.validate_excel_file(csv_content)
        print(f"   Validación: {'✅' if is_valid else '❌'} {message}")
        
        if is_valid:
            # Procesar
            result = processor.process_excel(csv_content)
            print(f"   Filas procesadas: {result['total_filas']}")
            print(f"   Columnas detectadas: {len(result['column_mapping'])}")
            
            # Mostrar mapeo de columnas
            print("   📋 Mapeo de columnas:")
            for field, info in result['column_mapping'].items():
                print(f"      • {field}: '{info['column']}' (confianza: {info['confidence']:.2f})")
        
    except FileNotFoundError:
        print("❌ No se encontró test_productos.csv")
    except Exception as e:
        print(f"❌ Error procesando CSV: {e}")
    
    print("\n" + "=" * 60)
    print("📝 INSTRUCCIONES PARA PROBAR EXCEL:")
    print("1. Crea un archivo Excel con estos datos:")
    print("   Nombre | Precio | Stock | Categoria")
    print("   Laptop | 1200   | 10    | Tecnologia")
    print("   Mouse  | 25     | 50    | Accesorios")
    print("")
    print("2. Guárdalo como:")
    print("   • Excel (.xlsx) - Libro de Excel")
    print("   • Excel 97-2003 (.xls) - Formato antiguo")
    print("   • CSV (.csv) - Valores separados por comas")
    print("")
    print("3. Coloca el archivo en este directorio y ejecuta:")
    print("   python test_excel_formats.py tu_archivo.xlsx")

def test_specific_file(filename):
    """Prueba un archivo específico."""
    
    print(f"\n🔍 PROBANDO ARCHIVO: {filename}")
    print("=" * 60)
    
    try:
        with open(filename, 'rb') as f:
            file_content = f.read()
        
        processor = ExcelProcessor()
        
        print(f"📄 Información del archivo:")
        print(f"   Tamaño: {len(file_content)} bytes")
        
        # Detectar tipo
        file_type = processor._detect_file_type(file_content)
        print(f"   Tipo detectado: {file_type}")
        
        # Validar
        is_valid, message = processor.validate_excel_file(file_content)
        print(f"   Validación: {'✅' if is_valid else '❌'} {message}")
        
        if not is_valid:
            print("❌ El archivo no es válido. Verifica el formato.")
            return
        
        # Obtener hojas (si es Excel)
        try:
            sheets = processor.get_sheet_names(file_content)
            print(f"   Hojas disponibles: {sheets}")
        except Exception as e:
            print(f"   ⚠️ Error obteniendo hojas: {e}")
        
        # Procesar archivo
        print("\n📊 Procesando archivo...")
        result = processor.process_excel(file_content)
        
        print(f"✅ Archivo procesado exitosamente:")
        print(f"   • Total filas: {result['total_filas']}")
        print(f"   • Columnas originales: {result['columnas_originales']}")
        print(f"   • Columnas reconocidas: {len(result['column_mapping'])}")
        print(f"   • Productos procesados: {len(result['productos_data'])}")
        print(f"   • Errores generales: {len(result['errores_generales'])}")
        
        # Mostrar mapeo de columnas
        print("\n📋 MAPEO DE COLUMNAS:")
        for field, info in result['column_mapping'].items():
            print(f"   • {field}: '{info['column']}' (confianza: {info['confidence']:.2f})")
        
        # Mostrar algunos productos
        print("\n📦 PRODUCTOS DETECTADOS:")
        for i, producto in enumerate(result['productos_data'][:3], 1):
            print(f"   {i}. {producto.get('nombre', 'Sin nombre')}")
            if producto.get('errores'):
                print(f"      ❌ Errores: {producto['errores']}")
            else:
                print(f"      ✅ Válido - Precio: ${producto.get('precio_venta', 0)}")
        
        if len(result['productos_data']) > 3:
            print(f"   ... y {len(result['productos_data']) - 3} productos más")
        
        # Mostrar errores si los hay
        if result['errores_generales']:
            print("\n❌ ERRORES GENERALES:")
            for error in result['errores_generales'][:3]:
                print(f"   • {error}")
        
    except FileNotFoundError:
        print(f"❌ No se encontró el archivo: {filename}")
    except Exception as e:
        print(f"❌ Error procesando archivo: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Probar archivo específico
        test_specific_file(sys.argv[1])
    else:
        # Probar detección general
        test_file_detection() 