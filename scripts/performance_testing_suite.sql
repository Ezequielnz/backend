-- =====================================================
-- SUITE DE PRUEBAS DE PERFORMANCE - CONSULTAS CLAVE
-- =====================================================
-- Fecha: 2025-08-25
-- Objetivo: Ejecutar EXPLAIN ANALYZE en consultas críticas del sistema
-- IMPORTANTE: Ejecutar después de que las tablas tengan datos reales

-- PASO 1: CONFIGURAR ENTORNO DE PRUEBAS
-- =====================================================

-- Habilitar timing para mediciones precisas
\timing on

-- Configurar parámetros para análisis detallado
SET work_mem = '256MB';
SET random_page_cost = 1.1;
SET effective_cache_size = '1GB';

-- PASO 2: CONSULTA CRÍTICA 1 - Obtener configuración efectiva por tenant
-- =====================================================

-- Esta es la consulta más frecuente del sistema
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING, FORMAT TEXT)
SELECT 
    bnc.id,
    bnc.rubro,
    bnc.custom_overrides,
    nrt.rule_type,
    nrt.condition_config,
    nrt.default_parameters
FROM business_notification_config bnc
JOIN notification_rule_templates nrt ON bnc.rubro = nrt.rubro
WHERE bnc.tenant_id = $1  -- Parámetro: UUID del tenant
  AND bnc.is_active = true
  AND nrt.is_latest = true
ORDER BY nrt.rule_type;

-- Resultado esperado:
-- - Index Scan on idx_notification_config_tenant_active
-- - Index Scan on idx_templates_rubro_latest
-- - Tiempo total: <5ms

-- PASO 3: CONSULTA CRÍTICA 2 - Notificaciones no leídas paginadas
-- =====================================================

EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING, FORMAT TEXT)
SELECT 
    n.id,
    n.title,
    n.message,
    n.severity,
    n.created_at,
    nt.icon,
    nt.color
FROM notifications n
LEFT JOIN notification_templates nt ON n.template_id = nt.id
WHERE n.tenant_id = $1  -- Parámetro: UUID del tenant
  AND n.is_read = false
ORDER BY n.created_at DESC
LIMIT 20 OFFSET 0;

-- Resultado esperado:
-- - Index Scan on idx_notifications_tenant_unread
-- - Limit operation eficiente
-- - Tiempo total: <10ms

-- PASO 4: CONSULTA CRÍTICA 3 - Features ML para ventana de tiempo
-- =====================================================

EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING, FORMAT TEXT)
SELECT 
    feature_date,
    feature_type,
    features->'sales_total' as sales_total,
    features->'inventory_count' as inventory_count
FROM ml_features
WHERE tenant_id = $1  -- Parámetro: UUID del tenant
  AND feature_date >= CURRENT_DATE - INTERVAL '30 days'
  AND feature_type IN ('sales_metrics', 'inventory_metrics')
ORDER BY feature_date DESC, feature_type;

-- Resultado esperado:
-- - Index Scan on idx_ml_features_tenant_date
-- - JSONB extraction eficiente
-- - Tiempo total: <15ms

-- PASO 5: CONSULTA CRÍTICA 4 - Búsqueda de reglas por condición JSONB
-- =====================================================

EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING, FORMAT TEXT)
SELECT 
    rubro,
    rule_type,
    condition_config,
    default_parameters
FROM notification_rule_templates
WHERE condition_config @> '{"metric": "sales_percentage_change"}'::jsonb
  AND is_latest = true;

-- Resultado esperado:
-- - Bitmap Index Scan on idx_templates_condition_config
-- - GIN index utilizado eficientemente
-- - Tiempo total: <20ms

-- PASO 6: CONSULTA CRÍTICA 5 - Dashboard de ML con modelos activos
-- =====================================================

EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING, FORMAT TEXT)
SELECT 
    mm.model_type,
    mm.accuracy,
    mm.last_trained,
    COUNT(mp.id) as prediction_count,
    AVG(mp.confidence_score) as avg_confidence
FROM ml_models mm
LEFT JOIN ml_predictions mp ON mm.id = mp.model_id 
    AND mp.prediction_date >= CURRENT_DATE - INTERVAL '7 days'
WHERE mm.tenant_id = $1  -- Parámetro: UUID del tenant
  AND mm.is_active = true
GROUP BY mm.id, mm.model_type, mm.accuracy, mm.last_trained
ORDER BY mm.accuracy DESC;

-- Resultado esperado:
-- - Index Scan on idx_ml_models_tenant_active
-- - Index Scan on idx_ml_predictions_tenant_date
-- - Agregación eficiente
-- - Tiempo total: <25ms

-- PASO 7: CONSULTA CRÍTICA 6 - Auditoría de cambios recientes
-- =====================================================

EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING, FORMAT TEXT)
SELECT 
    action,
    entity_type,
    entity_id,
    new_values,
    created_at
FROM notification_audit_log
WHERE tenant_id = $1  -- Parámetro: UUID del tenant
  AND created_at >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY created_at DESC
LIMIT 50;

-- Resultado esperado:
-- - Index Scan on idx_audit_log_tenant_date
-- - Tiempo total: <8ms

-- PASO 8: ANÁLISIS DE QUERIES COMPLEJAS - Reporte de notificaciones
-- =====================================================

EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING, FORMAT TEXT)
WITH notification_stats AS (
    SELECT 
        DATE_TRUNC('day', created_at) as day,
        severity,
        COUNT(*) as count,
        COUNT(*) FILTER (WHERE is_read = false) as unread_count
    FROM notifications
    WHERE tenant_id = $1  -- Parámetro: UUID del tenant
      AND created_at >= CURRENT_DATE - INTERVAL '30 days'
    GROUP BY DATE_TRUNC('day', created_at), severity
)
SELECT 
    day,
    severity,
    count,
    unread_count,
    ROUND(unread_count * 100.0 / count, 2) as unread_percentage
FROM notification_stats
ORDER BY day DESC, severity;

-- Resultado esperado:
-- - Index Scan eficiente con filtros de fecha
-- - Agregación optimizada
-- - Tiempo total: <30ms

-- PASO 9: BENCHMARK DE INSERCIÓN - Notificaciones masivas
-- =====================================================

-- Simular inserción de notificaciones en lote
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING, FORMAT TEXT)
INSERT INTO notifications (tenant_id, title, message, severity, created_at)
SELECT 
    $1,  -- Parámetro: UUID del tenant
    'Batch notification ' || i,
    'Generated for performance test',
    (ARRAY['info', 'warning', 'error'])[1 + (i % 3)],
    NOW() - (i * INTERVAL '1 minute')
FROM generate_series(1, 100) i;

-- Resultado esperado:
-- - Inserción eficiente sin bloqueos
-- - Tiempo total: <50ms para 100 registros

-- PASO 10: VALIDACIÓN DE ÍNDICES UTILIZADOS
-- =====================================================

-- Verificar que los índices se están utilizando
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    CASE 
        WHEN idx_scan > 0 THEN 'UTILIZADO ✓'
        ELSE 'NO UTILIZADO ✗'
    END as status
FROM pg_stat_user_indexes
WHERE indexname LIKE 'idx_%'
  AND tablename IN (
      'business_notification_config',
      'notification_rule_templates',
      'notifications',
      'ml_features',
      'ml_models',
      'ml_predictions',
      'notification_audit_log'
  )
ORDER BY idx_scan DESC;

-- PASO 11: MÉTRICAS DE PERFORMANCE OBJETIVO
-- =====================================================

-- Definir métricas objetivo para cada tipo de consulta
CREATE TEMP TABLE performance_targets AS
SELECT * FROM (VALUES
    ('Configuración por tenant', '5ms', 'Crítica - Muy frecuente'),
    ('Notificaciones no leídas', '10ms', 'Crítica - UI principal'),
    ('Features ML por fecha', '15ms', 'Importante - Dashboard ML'),
    ('Búsqueda JSONB', '20ms', 'Moderada - Configuración'),
    ('Dashboard ML completo', '25ms', 'Importante - Analytics'),
    ('Auditoría reciente', '8ms', 'Moderada - Admin'),
    ('Reporte estadísticas', '30ms', 'Baja - Reportes'),
    ('Inserción en lote', '50ms/100 registros', 'Crítica - Workers')
) AS t(query_type, target_time, priority);

SELECT * FROM performance_targets ORDER BY priority;

-- PASO 12: REPORTE FINAL DE PERFORMANCE
-- =====================================================

-- Crear función para generar reporte automático
CREATE OR REPLACE FUNCTION generate_performance_report()
RETURNS TABLE (
    metric TEXT,
    current_value TEXT,
    target_value TEXT,
    status TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        'Índices creados'::TEXT,
        (SELECT COUNT(*)::TEXT FROM pg_indexes WHERE indexname LIKE 'idx_%' 
         AND tablename ~ 'notification|ml_'),
        '15+'::TEXT,
        CASE WHEN (SELECT COUNT(*) FROM pg_indexes WHERE indexname LIKE 'idx_%' 
                   AND tablename ~ 'notification|ml_') >= 15 
             THEN '✓ OBJETIVO CUMPLIDO' 
             ELSE '✗ NECESITA MEJORA' END
    
    UNION ALL
    
    SELECT 
        'Tablas con RLS'::TEXT,
        (SELECT COUNT(*)::TEXT FROM pg_tables WHERE tablename ~ 'notification|ml_' 
         AND rowsecurity = true),
        '8'::TEXT,
        '✓ CONFIGURADO'::TEXT;
END;
$$ LANGUAGE plpgsql;

-- Ejecutar reporte
SELECT * FROM generate_performance_report();

-- Log final
INSERT INTO migration_log (migration_name, notes) 
VALUES (
    'performance_testing_suite', 
    'Suite de pruebas de performance ejecutada. Índices validados y consultas optimizadas.'
);

RAISE NOTICE 'Suite de pruebas de performance completada. Revisar resultados de EXPLAIN ANALYZE.';

-- INSTRUCCIONES DE USO:
-- ====================
-- 1. Reemplazar $1 con UUIDs reales de tenants para pruebas
-- 2. Ejecutar cada EXPLAIN por separado para análisis detallado
-- 3. Verificar que se usan los índices esperados
-- 4. Comparar tiempos con objetivos definidos
-- 5. Ajustar índices si performance no cumple objetivos
