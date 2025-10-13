from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

# Crear instancia de Celery
celery_app = Celery(
    "micropymes",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.notification_worker", "app.workers.ml_worker", "app.workers.maintenance_worker", "app.workers.embedding_worker", "app.workers.monitoring_worker"]
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
        "app.workers.monitoring_worker.*": {"queue": "monitoring"},
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
        # Phase 5: Drift detection - daily at 2 AM
        "detect-model-drift-daily": {
            "task": "app.workers.monitoring_worker.detect_drift_all_models",
            "schedule": crontab(hour=2, minute=0),
        },
        # Phase 5: Aggregate metrics - hourly
        "aggregate-performance-metrics-hourly": {
            "task": "app.workers.monitoring_worker.aggregate_hourly_metrics",
            "schedule": crontab(minute=0),
        },
        # Phase 5: Daily metric aggregation - daily at 1 AM
        "aggregate-daily-metrics": {
            "task": "app.workers.monitoring_worker.aggregate_daily_metrics",
            "schedule": crontab(hour=1, minute=0),
        },
        # Phase 5: Generate compliance reports - weekly (Monday 3 AM)
        "generate-compliance-reports-weekly": {
            "task": "app.workers.monitoring_worker.generate_weekly_compliance_report",
            "schedule": crontab(day_of_week=1, hour=3, minute=0),
        },
        # Phase 5: Process user feedback - every 6 hours
        "process-user-feedback": {
            "task": "app.workers.monitoring_worker.process_feedback_batch",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        # Phase 5: Check partitioning needs - daily at 4 AM
        "check-partitioning-needs": {
            "task": "app.workers.monitoring_worker.check_partitioning_needs",
            "schedule": crontab(hour=4, minute=0),
        },
    },
)

if __name__ == "__main__":
    celery_app.start()
