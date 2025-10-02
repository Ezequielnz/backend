from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

# Crear instancia de Celery
celery_app = Celery(
    "micropymes",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.notification_worker", "app.workers.ml_worker", "app.workers.maintenance_worker", "app.workers.embedding_worker"]
)

# Configuración de Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "app.workers.notification_worker.*": {"queue": "notifications"},
        "app.workers.ml_worker.*": {"queue": "ml_processing"},
    },
    beat_schedule={
        # Notificaciones diarias a las 8 AM
        "daily-notifications": {
            "task": "app.workers.notification_worker.send_daily_notifications",
            "schedule": crontab(hour=8, minute=0),
        },
        # Re-entrenamiento de modelos ML los lunes a las 2 AM
        "weekly-ml-retrain": {
            "task": "app.workers.ml_worker.retrain_all_models",
            "schedule": crontab(hour=2, minute=0, day_of_week=1),
        },
        # Verificación de reglas cada 5 minutos
        "check-notification-rules": {
            "task": "app.workers.notification_worker.check_notification_rules",
            "schedule": 300.0,
        },
        # Actualización de features ML cada hora
        "update-ml-features": {
            "task": "app.workers.ml_worker.update_business_features",
            "schedule": 3600.0,
        },
        # Limpieza de notificaciones antiguas (diario a medianoche)
        "cleanup-old-notifications": {
            "task": "app.workers.maintenance_worker.cleanup_old_notifications",
            "schedule": crontab(hour=0, minute=0),
        },
    },
)

if __name__ == "__main__":
    celery_app.start()
