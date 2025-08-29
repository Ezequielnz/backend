"""
Worker para procesamiento de notificaciones
"""
from app.celery_app import celery_app
from datetime import datetime, timezone
from supabase.client import create_client
from app.core.config import settings
from app.core.cache_decorators import invalidate_on_update
import logging

logger = logging.getLogger(__name__)

@celery_app.task(bind=True)
def send_daily_notifications(self):
    """
    Envía notificaciones diarias programadas (8 AM)
    """
    try:
        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        
        # Obtener negocios activos
        businesses = supabase.table("negocios").select("id, nombre").execute()
        
        notifications_sent = 0
        for business in businesses.data:
            # Aquí iría la lógica de notificaciones diarias
            logger.info(f"Procesando notificaciones diarias para negocio: {business['nombre']}")
            notifications_sent += 1
        
        return {
            "task": "daily_notifications",
            "businesses_processed": len(businesses.data),
            "notifications_sent": notifications_sent,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error en notificaciones diarias: {str(e)}")
        raise self.retry(exc=e, countdown=60, max_retries=3)

@celery_app.task(bind=True)
def check_notification_rules(self):
    """
    Verifica reglas de notificación cada 5 minutos
    """
    try:
        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        
        # Obtener reglas activas
        rules = supabase.table("business_notification_config").select("*").eq("is_active", True).execute()
        
        rules_processed = 0
        for rule in rules.data:
            # Aquí iría la lógica de evaluación de reglas
            logger.info(f"Evaluando regla: {rule['id']}")
            rules_processed += 1
        
        return {
            "task": "check_notification_rules", 
            "rules_processed": rules_processed,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error verificando reglas: {str(e)}")
        raise self.retry(exc=e, countdown=30, max_retries=5)

@celery_app.task(bind=True)
@invalidate_on_update('notifications')
def send_notification(self, business_id: str, notification_type: str, data: dict):
    """
    Envía una notificación específica
    """
    try:
        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        
        # Crear registro de notificación
        notification = {
            "tenant_id": business_id,
            "title": data.get("title") or f"Notificación: {notification_type}",
            "message": data.get("message") or str(data),
            "metadata": data,
            "severity": data.get("severity", "info"),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        result = supabase.table("notifications").insert(notification).execute()
        
        logger.info(f"Notificación enviada: {notification_type} para negocio {business_id}")
        
        return {
            "task": "send_notification",
            "notification_id": result.data[0]["id"] if result.data else None,
            "business_id": business_id,
            "type": notification_type,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error enviando notificación: {str(e)}")
        raise self.retry(exc=e, countdown=30, max_retries=3)
