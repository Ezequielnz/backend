"""
Worker para procesamiento de Machine Learning
"""
from app.celery_app import celery_app
from datetime import datetime, timezone, timedelta
from supabase.client import create_client
from app.core.config import settings
from app.core.cache_decorators import cache_ml_features, cache_ml_predictions, invalidate_on_update
import logging
import numpy as np

logger = logging.getLogger(__name__)

@celery_app.task(bind=True)
def retrain_all_models(self):
    """
    Re-entrena todos los modelos ML (lunes 2 AM)
    """
    try:
        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        
        # Obtener negocios activos
        businesses = supabase.table("businesses").select("id, name").eq("active", True).execute()
        
        models_retrained = 0
        for business in businesses.data:
            # Aquí iría la lógica de re-entrenamiento
            logger.info(f"Re-entrenando modelos para negocio: {business['name']}")
            models_retrained += 1
        
        return {
            "task": "retrain_all_models",
            "businesses_processed": len(businesses.data),
            "models_retrained": models_retrained,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error en re-entrenamiento: {str(e)}")
        raise self.retry(exc=e, countdown=300, max_retries=2)

@celery_app.task(bind=True)
@invalidate_on_update('ml_features')
def update_business_features(self):
    """
    Actualiza features ML cada hora
    """
    try:
        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        
        # Obtener negocios activos
        businesses = supabase.table("businesses").select("id, name").eq("active", True).execute()
        
        features_updated = 0
        for business in businesses.data:
            # Simular actualización de features
            features = {
                "business_id": business["id"],
                "sales_trend": np.random.random(),
                "inventory_level": np.random.random(),
                "customer_activity": np.random.random(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Guardar features en BD
            supabase.table("ml_features").upsert(features).execute()
            features_updated += 1
            
            logger.info(f"Features actualizadas para negocio: {business['name']}")
        
        return {
            "task": "update_business_features",
            "businesses_processed": len(businesses.data),
            "features_updated": features_updated,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error actualizando features: {str(e)}")
        raise self.retry(exc=e, countdown=60, max_retries=3)

@celery_app.task(bind=True)
@cache_ml_predictions(ttl=1800)
def generate_predictions(self, business_id: str, prediction_type: str):
    """
    Genera predicciones ML para un negocio específico
    """
    try:
        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        
        # Obtener datos históricos (simulado)
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30)
        
        # Simular predicción
        prediction_value = np.random.uniform(1000, 5000)
        confidence = np.random.uniform(0.7, 0.95)
        
        # Guardar predicción
        prediction = {
            "business_id": business_id,
            "type": prediction_type,
            "value": prediction_value,
            "confidence": confidence,
            "model_version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        result = supabase.table("ml_predictions").insert(prediction).execute()
        
        logger.info(f"Predicción generada: {prediction_type} para negocio {business_id}")
        
        return {
            "task": "generate_predictions",
            "business_id": business_id,
            "prediction_type": prediction_type,
            "prediction_id": result.data[0]["id"] if result.data else None,
            "value": prediction_value,
            "confidence": confidence,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error generando predicción: {str(e)}")
        raise self.retry(exc=e, countdown=60, max_retries=3)

@celery_app.task(bind=True)
@cache_ml_features(ttl=3600)
def analyze_business_trends(self, business_id: str):
    """
    Analiza tendencias de negocio
    """
    try:
        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        
        # Obtener datos del negocio
        business = supabase.table("businesses").select("*").eq("id", business_id).single().execute()
        
        if not business.data:
            raise ValueError(f"Negocio {business_id} no encontrado")
        
        # Simular análisis de tendencias
        trends = {
            "sales_growth": np.random.uniform(-0.1, 0.3),
            "customer_retention": np.random.uniform(0.6, 0.9),
            "inventory_turnover": np.random.uniform(2, 8),
            "profit_margin": np.random.uniform(0.1, 0.4)
        }
        
        logger.info(f"Análisis de tendencias completado para negocio: {business.data['name']}")
        
        return {
            "task": "analyze_business_trends",
            "business_id": business_id,
            "business_name": business.data["name"],
            "trends": trends,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error analizando tendencias: {str(e)}")
        raise self.retry(exc=e, countdown=60, max_retries=3)
