"""
Worker para tareas de mantenimiento del sistema
"""
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

try:
    from app.celery_app import celery_app
    logger.info("Successfully imported celery_app")
except ImportError as e:
    logger.error(f"Failed to import celery_app: {e}")
    raise

try:
    from app.db.supabase_client import get_supabase_service_client
    logger.info("Successfully imported get_supabase_service_client")
except ImportError as e:
    logger.error(f"Failed to import get_supabase_service_client: {e}")
    raise

logger = logging.getLogger(__name__)

@celery_app.task(bind=True)
def cleanup_old_notifications(self):
    """
    Limpia notificaciones antiguas (más de 30 días)
    """
    try:
        supabase = get_supabase_service_client()
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
        
        # Eliminar notificaciones antiguas
        result = supabase.table("notifications").delete().lt(
            "created_at", cutoff_date.isoformat()
        ).execute()
        
        logger.info(f"Limpieza completada: {len(result.data)} notificaciones eliminadas")
        return {"deleted_count": len(result.data)}
        
    except Exception as e:
        logger.error(f"Error en limpieza de notificaciones: {str(e)}")
        raise self.retry(exc=e, countdown=60, max_retries=3)

@celery_app.task(bind=True)
def cleanup_old_ml_predictions(self):
    """
    Limpia predicciones ML antiguas (más de 90 días)
    """
    try:
        supabase = get_supabase_service_client()
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=90)
        
        # Eliminar predicciones antiguas
        result = supabase.table("ml_predictions").delete().lt(
            "created_at", cutoff_date.isoformat()
        ).execute()
        
        logger.info(f"Limpieza ML completada: {len(result.data)} predicciones eliminadas")
        return {"deleted_count": len(result.data)}
        
    except Exception as e:
        logger.error(f"Error en limpieza de predicciones ML: {str(e)}")
        raise self.retry(exc=e, countdown=60, max_retries=3)

@celery_app.task(bind=True)
def health_check(self):
    """
    Verificación de salud del sistema
    """
    try:
        supabase = get_supabase_service_client()
        
        # Test conexión a Supabase
        result = supabase.table("tenant_settings").select("tenant_id").limit(1).execute()
        
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "supabase_connection": "ok"
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        }
