#!/usr/bin/env python3
"""
Script de mantenimiento para limpiar datos temporales.

Uso:
    python scripts/maintenance.py

Este script puede ser ejecutado manualmente o programado como tarea cron.
"""

import sys
import os
import asyncio

# Agregar el directorio raíz al path para importar módulos de la app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.tasks.maintenance import MaintenanceTasks

async def main():
    """Función principal del script de mantenimiento."""
    print("🔧 Iniciando script de mantenimiento...")
    
    try:
        maintenance = MaintenanceTasks()
        await maintenance.ejecutar_mantenimiento_completo()
        print("✅ Script de mantenimiento completado exitosamente")
        
    except Exception as e:
        print(f"❌ Error en script de mantenimiento: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 