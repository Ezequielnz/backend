#!/usr/bin/env python3
"""
Script de prueba para la funcionalidad de importación de productos.
"""

import asyncio
import sys
import os

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from app.services.importacion_productos import ImportacionProductosService

async def test_import():
    """Prueba la funcionalidad de importación."""
    
    print("🧪 PROBANDO FUNCIONALIDAD DE IMPORTACIÓN")
    print("=" * 50)
    
    # Leer archivo de prueba
    try:
        with open('test_productos.csv', 'rb') as f:
            file_content = f.read()
        print(f"✅ Archivo leído: {len(file_content)} bytes")
    except FileNotFoundError:
        print("❌ No se encontró el archivo test_productos.csv")
        return
    
    # Crear servicio
    service = ImportacionProductosService()
    
    # IDs de prueba (estos deberían ser IDs reales de tu base de datos)
    negocio_id = "test-negocio-id"
    usuario_id = "test-usuario-id"
    
    try:
        # Procesar archivo
        print("\n📤 Procesando archivo...")
        resultado = await service.procesar_archivo_excel(
            file_content=file_content,
            negocio_id=negocio_id,
            usuario_id=usuario_id
        )
        
        print(f"✅ Archivo procesado:")
        print(f"   • Total filas: {resultado.total_filas}")
        print(f"   • Filas procesadas: {resultado.filas_procesadas}")
        print(f"   • Filas válidas: {resultado.filas_validas}")
        print(f"   • Filas con errores: {resultado.filas_con_errores}")
        print(f"   • Productos temporales: {len(resultado.productos_temporales)}")
        
        if resultado.errores_generales:
            print(f"   • Errores generales: {resultado.errores_generales}")
        
        # Mostrar productos temporales
        print("\n📋 PRODUCTOS TEMPORALES:")
        for i, producto in enumerate(resultado.productos_temporales[:3], 1):  # Solo primeros 3
            print(f"   {i}. {producto.nombre} - ${producto.precio_venta}")
            if producto.errores:
                print(f"      ❌ Errores: {producto.errores}")
            else:
                print(f"      ✅ Válido")
        
        if len(resultado.productos_temporales) > 3:
            print(f"   ... y {len(resultado.productos_temporales) - 3} más")
        
        # Obtener resumen
        print("\n📊 Obteniendo resumen...")
        try:
            resumen = await service.obtener_resumen_importacion(negocio_id, usuario_id)
            print(f"✅ Resumen obtenido:")
            print(f"   • Total filas: {resumen.total_filas}")
            print(f"   • Productos válidos: {resumen.productos_validos}")
            print(f"   • Productos con errores: {resumen.productos_con_errores}")
            print(f"   • Categorías nuevas: {len(resumen.categorias_nuevas)}")
        except Exception as e:
            print(f"⚠️ Error al obtener resumen: {e}")
        
        # Limpiar datos temporales
        print("\n🧹 Limpiando datos temporales...")
        await service.cancelar_importacion(negocio_id, usuario_id)
        print("✅ Datos temporales limpiados")
        
    except Exception as e:
        print(f"❌ Error durante la prueba: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_import()) 