"""
Tareas de mantenimiento para limpieza automática de datos.
"""

import asyncio
import logging
from datetime import datetime
from app.services.importacion_productos import ImportacionProductosService

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MaintenanceTasks:
    """Tareas de mantenimiento del sistema."""
    
    def __init__(self):
        self.importacion_service = ImportacionProductosService()
    
    async def limpiar_datos_temporales(self) -> None:
        """
        Limpia datos temporales antiguos de importaciones.
        Se ejecuta automáticamente para mantener la base de datos limpia.
        """
        try:
            logger.info("Iniciando limpieza de datos temporales...")
            
            registros_eliminados = await self.importacion_service.limpiar_importaciones_antiguas()
            
            if registros_eliminados > 0:
                logger.info(f"✅ Limpieza completada: {registros_eliminados} registros eliminados")
            else:
                logger.info("✅ No hay datos temporales antiguos para limpiar")
                
        except Exception as e:
            logger.error(f"❌ Error en limpieza de datos temporales: {str(e)}")
    
    async def ejecutar_mantenimiento_completo(self) -> None:
        """
        Ejecuta todas las tareas de mantenimiento.
        """
        logger.info(f"🔧 Iniciando mantenimiento completo - {datetime.now()}")
        
        # Limpiar datos temporales
        await self.limpiar_datos_temporales()
        
        # Aquí se pueden agregar más tareas de mantenimiento en el futuro
        # Por ejemplo: limpiar logs antiguos, optimizar índices, etc.
        
        logger.info("🎉 Mantenimiento completo finalizado")

# Función para ejecutar mantenimiento desde línea de comandos
async def main():
    """Función principal para ejecutar mantenimiento."""
    maintenance = MaintenanceTasks()
    await maintenance.ejecutar_mantenimiento_completo()

if __name__ == "__main__":
    asyncio.run(main()) 