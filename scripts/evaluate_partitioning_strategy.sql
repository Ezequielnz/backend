-- =====================================================
-- EVALUACIÓN DE ESTRATEGIA DE PARTICIONADO
-- =====================================================
-- Fecha: 2025-08-25
-- Objetivo: Evaluar necesidad de particionado para alto volumen
-- IMPORTANTE: Ejecutar después de optimize_indexes_performance.sql

-- PASO 1: ANÁLISIS DE VOLUMEN ACTUAL Y PROYECTADO
-- =====================================================

-- Función para estimar volumen futuro basado en crecimiento
CREATE OR REPLACE FUNCTION estimate_table_growth(
    table_name TEXT,
    months_projection INTEGER DEFAULT 12
) RETURNS TABLE (
    current_rows BIGINT,
    projected_rows BIGINT,
    current_size TEXT,
    projected_size TEXT,
    partition_recommended BOOLEAN
) AS $$
DECLARE
    current_count BIGINT;
    table_size BIGINT;
    growth_factor NUMERIC := 2.5; -- Factor de crecimiento conservador
BEGIN
    -- Obtener conteo actual (simulado para tablas nuevas)
    EXECUTE format('SELECT COALESCE(COUNT(*), 0) FROM %I', table_name) INTO current_count;
    
    -- Estimar crecimiento basado en número de negocios
    IF table_name = 'notification_rule_templates' THEN
        -- Templates crecen con nuevos rubros y versiones
        current_count := GREATEST(current_count, 100); -- Mínimo estimado
        growth_factor := 1.5; -- Crecimiento moderado
    ELSIF table_name = 'notifications' THEN
        -- Notificaciones crecen exponencialmente con usuarios
        current_count := GREATEST(current_count, 1000); -- Mínimo estimado
        growth_factor := 5.0; -- Crecimiento alto
    ELSIF table_name = 'ml_features' THEN
        -- Features crecen diariamente por tenant
        current_count := GREATEST(current_count, 500); -- Mínimo estimado
        growth_factor := 10.0; -- Crecimiento muy alto
    END IF;
    
    -- Calcular proyecciones
    current_rows := current_count;
    projected_rows := (current_count * growth_factor * months_projection / 12)::BIGINT;
    
    -- Estimar tamaños (aproximado)
    table_size := current_count * 1024; -- 1KB promedio por row
    current_size := pg_size_pretty(table_size);
    projected_size := pg_size_pretty((projected_rows * 1024)::BIGINT);
    
    -- Recomendar particionado si se proyectan >1M rows
    partition_recommended := projected_rows > 1000000;
    
    RETURN NEXT;
END;
$$ LANGUAGE plpgsql;

-- PASO 2: EVALUACIÓN POR TABLA
-- =====================================================

-- Evaluar notification_rule_templates
SELECT 
    'notification_rule_templates' as tabla,
    current_rows,
    projected_rows,
    current_size,
    projected_size,
    partition_recommended,
    CASE 
        WHEN partition_recommended THEN 'Particionar por rubro'
        ELSE 'Índices suficientes'
    END as recomendacion
FROM estimate_table_growth('notification_rule_templates', 24);

-- Evaluar notifications
SELECT 
    'notifications' as tabla,
    current_rows,
    projected_rows,
    current_size,
    projected_size,
    partition_recommended,
    CASE 
        WHEN partition_recommended THEN 'Particionar por fecha (mensual)'
        ELSE 'Índices suficientes'
    END as recomendacion
FROM estimate_table_growth('notifications', 24);

-- Evaluar ml_features
SELECT 
    'ml_features' as tabla,
    current_rows,
    projected_rows,
    current_size,
    projected_size,
    partition_recommended,
    CASE 
        WHEN partition_recommended THEN 'Particionar por fecha (trimestral)'
        ELSE 'Índices suficientes'
    END as recomendacion
FROM estimate_table_growth('ml_features', 24);

-- PASO 3: ESTRATEGIA DE PARTICIONADO PARA NOTIFICATION_RULE_TEMPLATES
-- =====================================================

-- Script para crear particionado por rubro (SOLO SI ES NECESARIO)
-- IMPORTANTE: Ejecutar solo si el análisis anterior lo recomienda

/*
-- Crear tabla principal particionada
CREATE TABLE notification_rule_templates_partitioned (
    LIKE notification_rule_templates INCLUDING ALL
) PARTITION BY LIST (rubro);

-- Crear particiones por rubro principales
CREATE TABLE notification_rule_templates_general 
PARTITION OF notification_rule_templates_partitioned FOR VALUES IN ('general');

CREATE TABLE notification_rule_templates_restaurante 
PARTITION OF notification_rule_templates_partitioned FOR VALUES IN ('restaurante');

CREATE TABLE notification_rule_templates_retail 
PARTITION OF notification_rule_templates_partitioned FOR VALUES IN ('retail');

CREATE TABLE notification_rule_templates_servicios 
PARTITION OF notification_rule_templates_partitioned FOR VALUES IN ('servicios');

-- Partición por defecto para otros rubros
CREATE TABLE notification_rule_templates_otros 
PARTITION OF notification_rule_templates_partitioned DEFAULT;

-- Migrar datos existentes
INSERT INTO notification_rule_templates_partitioned 
SELECT * FROM notification_rule_templates;

-- Renombrar tablas (requiere downtime mínimo)
ALTER TABLE notification_rule_templates RENAME TO notification_rule_templates_old;
ALTER TABLE notification_rule_templates_partitioned RENAME TO notification_rule_templates;
*/

-- PASO 4: ESTRATEGIA DE PARTICIONADO PARA NOTIFICATIONS
-- =====================================================

-- Script para crear particionado por fecha (SOLO SI ES NECESARIO)

/*
-- Crear tabla principal particionada por rango de fechas
CREATE TABLE notifications_partitioned (
    LIKE notifications INCLUDING ALL
) PARTITION BY RANGE (created_at);

-- Crear particiones mensuales (ejemplo para 2025)
CREATE TABLE notifications_2025_01 
PARTITION OF notifications_partitioned 
FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE notifications_2025_02 
PARTITION OF notifications_partitioned 
FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');

-- Función para crear particiones automáticamente
CREATE OR REPLACE FUNCTION create_monthly_partition(table_name TEXT, start_date DATE)
RETURNS VOID AS $$
DECLARE
    partition_name TEXT;
    end_date DATE;
BEGIN
    partition_name := table_name || '_' || to_char(start_date, 'YYYY_MM');
    end_date := start_date + INTERVAL '1 month';
    
    EXECUTE format('CREATE TABLE %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
                   partition_name, table_name, start_date, end_date);
END;
$$ LANGUAGE plpgsql;
*/

-- PASO 5: EVALUACIÓN DE PERFORMANCE CON PARTICIONADO
-- =====================================================

-- Función para comparar performance con y sin particionado
CREATE OR REPLACE FUNCTION compare_query_performance()
RETURNS TABLE (
    query_type TEXT,
    without_partition_ms NUMERIC,
    with_partition_ms NUMERIC,
    improvement_factor NUMERIC
) AS $$
BEGIN
    -- Simulación de mejoras esperadas con particionado
    RETURN QUERY VALUES 
        ('Consulta por rubro específico', 100.0, 15.0, 6.7),
        ('Consulta por fecha reciente', 200.0, 25.0, 8.0),
        ('Consulta cross-partition', 50.0, 120.0, 0.4), -- Empeora
        ('Inserción de datos', 10.0, 12.0, 0.8); -- Ligeramente peor
END;
$$ LANGUAGE plpgsql;

-- Mostrar comparación de performance
SELECT * FROM compare_query_performance();

-- PASO 6: RECOMENDACIONES FINALES
-- =====================================================

-- Análisis de costo-beneficio del particionado
WITH partition_analysis AS (
    SELECT 
        'notification_rule_templates' as tabla,
        'rubro' as partition_key,
        'Bajo volumen inicial' as current_state,
        'Considerar cuando >100K templates' as threshold,
        'Mejora consultas por rubro específico' as benefits,
        'Complejidad en mantenimiento' as drawbacks
    
    UNION ALL
    
    SELECT 
        'notifications' as tabla,
        'created_at (mensual)' as partition_key,
        'Crecimiento exponencial esperado' as current_state,
        'Implementar cuando >1M notificaciones' as threshold,
        'Mejora consultas por fecha, archivado automático' as benefits,
        'Gestión de particiones automática requerida' as drawbacks
    
    UNION ALL
    
    SELECT 
        'ml_features' as tabla,
        'feature_date (trimestral)' as partition_key,
        'Crecimiento alto con ML activo' as current_state,
        'Implementar cuando >500K features' as threshold,
        'Mejora consultas por ventanas de tiempo' as benefits,
        'Complejidad en queries cross-partition' as drawbacks
)
SELECT * FROM partition_analysis;

-- PASO 7: PLAN DE IMPLEMENTACIÓN GRADUAL
-- =====================================================

-- Crear plan de implementación basado en métricas
INSERT INTO migration_log (migration_name, notes) 
VALUES (
    'evaluate_partitioning_strategy', 
    'Evaluación de particionado completada. Recomendación: Implementar índices primero, evaluar particionado cuando se alcancen umbrales de volumen específicos.'
);

-- Crear tabla de monitoreo para decidir cuándo particionar
CREATE TABLE IF NOT EXISTS partition_monitoring (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL,
    row_count BIGINT NOT NULL,
    table_size_bytes BIGINT NOT NULL,
    avg_query_time_ms NUMERIC,
    partition_recommended BOOLEAN DEFAULT false,
    checked_at TIMESTAMP DEFAULT NOW()
);

-- Función para monitoreo automático
CREATE OR REPLACE FUNCTION check_partition_thresholds()
RETURNS TABLE (
    table_name TEXT,
    should_partition BOOLEAN,
    reason TEXT
) AS $$
BEGIN
    -- Lógica de evaluación automática
    RETURN QUERY
    SELECT 
        'notification_rule_templates'::TEXT,
        (SELECT COUNT(*) FROM notification_rule_templates) > 100000,
        'Más de 100K templates'::TEXT
    
    UNION ALL
    
    SELECT 
        'notifications'::TEXT,
        (SELECT COUNT(*) FROM notifications) > 1000000,
        'Más de 1M notificaciones'::TEXT;
END;
$$ LANGUAGE plpgsql;

RAISE NOTICE 'Evaluación de particionado completada. Revisar recomendaciones en los resultados.';

-- COMENTARIOS SOBRE ESTRATEGIA DE PARTICIONADO:
-- =============================================
-- 1. IMPLEMENTACIÓN GRADUAL: Empezar con índices, evaluar particionado según crecimiento
-- 2. UMBRALES CLAROS: Definir métricas específicas para activar particionado
-- 3. MONITOREO AUTOMÁTICO: Función para evaluar cuándo es necesario particionar
-- 4. COSTO-BENEFICIO: Considerar complejidad vs beneficios de performance
-- 5. PARTICIONADO POR RUBRO: Útil para queries específicas por sector
-- 6. PARTICIONADO POR FECHA: Esencial para datos temporales con alto volumen
