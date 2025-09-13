"""
Worker para procesamiento de notificaciones
"""
from app.celery_app import celery_app
from datetime import datetime, timezone
from typing import Callable, cast
from app.db.supabase_client import get_supabase_service_client, TableQueryProto, APIResponseProto
from app.core.cache_decorators import invalidate_on_update
import logging

logger = logging.getLogger(__name__)

@celery_app.task(bind=True)
def send_daily_notifications(self) -> dict[str, object]:
    """
    Envía notificaciones diarias programadas (8 AM)
    """
    try:
        supabase = get_supabase_service_client()
        table_fn: Callable[[str], object] = cast(Callable[[str], object], getattr(supabase, "table"))
        tbl: TableQueryProto = cast(TableQueryProto, table_fn("negocios"))
        res: APIResponseProto = tbl.select("id, nombre").execute()
        data_obj: object = getattr(res, "data", []) or []
        businesses: list[dict[str, object]] = cast(list[dict[str, object]], data_obj) if isinstance(data_obj, list) else []

        notifications_sent = 0
        for business in businesses:
            nombre = cast(str, business.get("nombre", ""))
            logger.info(f"Procesando notificaciones diarias para negocio: {nombre}")
            notifications_sent += 1

        return {
            "task": "daily_notifications",
            "businesses_processed": len(businesses),
            "notifications_sent": notifications_sent,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Error en notificaciones diarias: {str(e)}")
        raise self.retry(exc=e, countdown=60, max_retries=3)

@celery_app.task(bind=True)
def check_notification_rules(self) -> dict[str, object]:
    """
    Verifica reglas de notificación cada 5 minutos
    """
    try:
        supabase = get_supabase_service_client()
        table_fn: Callable[[str], object] = cast(Callable[[str], object], getattr(supabase, "table"))
        tbl: TableQueryProto = cast(TableQueryProto, table_fn("business_notification_config"))
        res: APIResponseProto = tbl.select("*").eq("is_active", True).execute()
        data_obj: object = getattr(res, "data", []) or []
        rules: list[dict[str, object]] = cast(list[dict[str, object]], data_obj) if isinstance(data_obj, list) else []

        rules_processed = 0
        for rule in rules:
            rule_id = rule.get("id")
            logger.info(f"Evaluando regla: {rule_id}")
            rules_processed += 1

        return {
            "task": "check_notification_rules",
            "rules_processed": rules_processed,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Error verificando reglas: {str(e)}")
        raise self.retry(exc=e, countdown=30, max_retries=5)

@celery_app.task(bind=True)
@invalidate_on_update('notifications')
def send_notification(self, business_id: str, notification_type: str, data: dict[str, object]) -> dict[str, object]:
    """
    Envía una notificación específica
    """
    try:
        supabase = get_supabase_service_client()
        notification: dict[str, object] = {
            "tenant_id": business_id,
            "title": cast(object, data.get("title")) or f"Notificación: {notification_type}",
            "message": cast(object, data.get("message")) or str(data),
            "metadata": data,
            "severity": cast(object, data.get("severity", "info")),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        table_fn: Callable[[str], object] = cast(Callable[[str], object], getattr(supabase, "table"))
        tbl: TableQueryProto = cast(TableQueryProto, table_fn("notifications"))
        res: APIResponseProto = tbl.insert(notification).execute()
        data_obj: object = getattr(res, "data", []) or []
        inserted: list[dict[str, object]] = cast(list[dict[str, object]], data_obj) if isinstance(data_obj, list) else []
        notif_id = (inserted[0].get("id") if inserted else None)  # type: ignore[union-attr]

        logger.info(f"Notificación enviada: {notification_type} para negocio {business_id}")

        return {
            "task": "send_notification",
            "notification_id": notif_id,
            "business_id": business_id,
            "type": notification_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Error enviando notificación: {str(e)}")
        raise self.retry(exc=e, countdown=30, max_retries=3)
