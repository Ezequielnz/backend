-- =====================================================
-- OPTIMIZACIÓN DE ÍNDICES Y PERFORMANCE
-- =====================================================
-- Fecha: 2025-08-25
-- Objetivo: Crear índices optimizados para consultas clave del sistema de notificaciones
-- IMPORTANTE: Ejecutar después de create_notifications_ml_schema.sql

-- PASO 1: ANÁLISIS DE CONSULTAS CLAVE
-- =====================================================
-- Identificar patrones de consulta más frecuentes:
-- 1. Obtener configuración activa por tenant
-- 2. Buscar reglas por rubro y versión latest
-- 3. Consultar notificaciones no leídas por tenant
-- 4. Buscar features ML por tenant y fecha
-- 5. Obtener modelos activos por tenant

-- PASO 2: ÍNDICES RECOMENDADOS PARA BUSINESS_NOTIFICATION_CONFIG
-- =====================================================

-- Índice compuesto para consultas de configuración activa por tenant
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notification_config_tenant_active
ON business_notification_config(tenant_id, is_active) 
WHERE is_active = true;

-- Índice para consultas por rubro (análisis y reporting)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notification_config_rubro
ON business_notification_config(rubro, is_active) 
WHERE is_active = true;

-- Índice para consultas de auditoría por fecha de actualización
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notification_config_updated
ON business_notification_config(updated_at DESC) 
WHERE is_active = true;

-- PASO 3: ÍNDICES PARA NOTIFICATION_RULE_TEMPLATES
-- =====================================================

-- Índice compuesto para consultas de templates por rubro y versión latest
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_templates_rubro_latest
ON notification_rule_templates(rubro, rule_type, is_latest) 
WHERE is_latest = true;

-- Índice para consultas por versión específica
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_templates_version
ON notification_rule_templates(rubro, rule_type, version);

-- Índice GIN para búsquedas en configuración JSONB
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_templates_condition_config
ON notification_rule_templates USING GIN (condition_config);

-- Índice GIN para búsquedas en parámetros JSONB
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_templates_parameters
ON notification_rule_templates USING GIN (default_parameters);

-- PASO 4: ÍNDICES PARA NOTIFICATIONS
-- =====================================================

-- Índice compuesto para consultas de notificaciones no leídas por tenant
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notifications_tenant_unread
ON notifications(tenant_id, is_read, created_at DESC) 
WHERE is_read = false;

-- Índice para consultas por usuario específico
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notifications_user_unread
ON notifications(user_id, is_read, created_at DESC) 
WHERE is_read = false AND user_id IS NOT NULL;

-- Índice para consultas por severidad
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notifications_severity
ON notifications(tenant_id, severity, created_at DESC) 
WHERE severity IN ('error', 'warning');

-- Índice GIN para búsquedas en metadata JSONB
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notifications_metadata
ON notifications USING GIN (metadata);

-- PASO 5: ÍNDICES PARA ML_FEATURES
-- =====================================================

-- Índice compuesto para consultas de features por tenant y fecha
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ml_features_tenant_date
ON ml_features(tenant_id, feature_date DESC, feature_type);

-- Índice para consultas por tipo de feature
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ml_features_type_date
ON ml_features(feature_type, feature_date DESC);

-- Índice GIN para búsquedas en features JSONB
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ml_features_data
ON ml_features USING GIN (features);

-- Índice para consultas de rango de fechas (ventanas de tiempo para ML)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ml_features_date_range
ON ml_features(feature_date, tenant_id, feature_type);

-- PASO 6: ÍNDICES PARA ML_MODELS
-- =====================================================

-- Índice compuesto para consultas de modelos activos por tenant
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ml_models_tenant_active
ON ml_models(tenant_id, model_type, is_active) 
WHERE is_active = true;

-- Índice para consultas por accuracy (mejores modelos)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ml_models_accuracy
ON ml_models(model_type, accuracy DESC, last_trained DESC) 
WHERE is_active = true;

-- Índice para consultas por fecha de entrenamiento
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ml_models_trained
ON ml_models(last_trained DESC, model_type) 
WHERE is_active = true;

-- PASO 7: ÍNDICES PARA ML_PREDICTIONS
-- =====================================================

-- Índice compuesto para consultas de predicciones por tenant y fecha
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ml_predictions_tenant_date
ON ml_predictions(tenant_id, prediction_date DESC, prediction_type);

-- Índice para consultas por confidence score (predicciones más confiables)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ml_predictions_confidence
ON ml_predictions(prediction_type, confidence_score DESC, prediction_date DESC);

-- Índice GIN para búsquedas en valores predichos JSONB
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ml_predictions_values
ON ml_predictions USING GIN (predicted_values);

-- PASO 8: ÍNDICES PARA NOTIFICATION_AUDIT_LOG
-- =====================================================

-- Índice compuesto para consultas de auditoría por tenant y fecha
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_log_tenant_date
ON notification_audit_log(tenant_id, created_at DESC);

-- Índice para consultas por acción y tipo de entidad
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_log_action_entity
ON notification_audit_log(action, entity_type, created_at DESC);

-- PASO 9: ESTADÍSTICAS Y MANTENIMIENTO
-- =====================================================

-- Actualizar estadísticas para el optimizador de consultas
ANALYZE business_notification_config;
ANALYZE notification_rule_templates;
ANALYZE notification_templates;
ANALYZE notifications;
ANALYZE ml_features;
ANALYZE ml_models;
ANALYZE ml_predictions;
ANALYZE notification_audit_log;

-- PASO 10: VALIDACIÓN DE ÍNDICES CREADOS
-- =====================================================

-- Verificar que todos los índices se crearon correctamente
SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes 
WHERE tablename IN (
    'business_notification_config',
    'notification_rule_templates',
    'notifications',
    'ml_features',
    'ml_models',
    'ml_predictions',
    'notification_audit_log'
)
AND indexname LIKE 'idx_%'
ORDER BY tablename, indexname;

-- Verificar tamaño de índices
SELECT 
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexname::regclass)) as index_size
FROM pg_indexes 
WHERE tablename IN (
    'business_notification_config',
    'notification_rule_templates',
    'notifications',
    'ml_features',
    'ml_models',
    'ml_predictions'
)
AND indexname LIKE 'idx_%'
ORDER BY pg_relation_size(indexname::regclass) DESC;

-- Log de optimización de índices
INSERT INTO migration_log (migration_name, notes) 
VALUES (
    'optimize_indexes_performance', 
    CONCAT(
        'Creados índices optimizados para performance. ',
        'Total índices: ', (
            SELECT COUNT(*) FROM pg_indexes 
            WHERE tablename IN (
                'business_notification_config', 'notification_rule_templates',
                'notifications', 'ml_features', 'ml_models', 'ml_predictions'
            ) AND indexname LIKE 'idx_%'
        )
    )
);

RAISE NOTICE 'Índices de performance creados exitosamente';

-- COMENTARIOS SOBRE ESTRATEGIA DE ÍNDICES:
-- ========================================
-- 1. CONCURRENTLY: Creación sin bloqueo de tablas
-- 2. Índices parciales con WHERE: Reducen tamaño y mejoran performance
-- 3. Índices compuestos: Optimizan consultas multi-columna frecuentes
-- 4. GIN para JSONB: Permiten búsquedas eficientes en datos semi-estructurados
-- 5. Orden DESC en fechas: Optimiza consultas de datos recientes
-- 6. Índices por severidad/tipo: Filtros frecuentes en la aplicación
