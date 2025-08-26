-- =====================================================
-- MIGRACIÓN DE DATOS: CONFIGURACIONES EXISTENTES AL NUEVO ESQUEMA
-- =====================================================
-- Fecha: 2025-08-25
-- Objetivo: Migrar configuraciones existentes sin downtime
-- IMPORTANTE: Ejecutar DESPUÉS de disable_triggers_migration.sql

-- PASO 1: ANÁLISIS DE DATOS EXISTENTES
-- =====================================================
-- Verificar tenant_settings existentes con rubro
SELECT 
    tenant_id,
    rubro,
    locale,
    timezone,
    currency,
    sales_drop_threshold,
    min_days_for_model,
    created_at
FROM tenant_settings 
WHERE rubro IS NOT NULL
ORDER BY created_at DESC;

-- Contar negocios sin configuración de notificaciones
SELECT 
    COUNT(*) as negocios_sin_config,
    COUNT(CASE WHEN ts.rubro IS NOT NULL THEN 1 END) as negocios_con_rubro
FROM negocios n
LEFT JOIN tenant_settings ts ON n.id = ts.tenant_id;

-- PASO 2: MIGRACIÓN DE CONFIGURACIONES EXISTENTES
-- =====================================================
-- Migrar tenant_settings con rubro a business_notification_config
INSERT INTO business_notification_config (
    tenant_id,
    rubro,
    template_version,
    custom_overrides,
    is_active,
    created_at,
    updated_at
)
SELECT 
    ts.tenant_id,
    COALESCE(ts.rubro, 'general') as rubro,
    'latest' as template_version,
    CASE 
        WHEN ts.sales_drop_threshold IS NOT NULL THEN
            jsonb_build_object(
                'sales_drop', jsonb_build_object(
                    'parameters', jsonb_build_object(
                        'threshold_percentage', ts.sales_drop_threshold
                    ),
                    'is_active', true
                )
            )
        ELSE '{}'::jsonb
    END as custom_overrides,
    true as is_active,
    ts.created_at,
    NOW()
FROM tenant_settings ts
WHERE ts.tenant_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM business_notification_config bnc 
      WHERE bnc.tenant_id = ts.tenant_id
  );

-- PASO 3: MIGRACIÓN DE NEGOCIOS SIN CONFIGURACIÓN
-- =====================================================
-- Crear configuración básica para negocios sin tenant_settings
INSERT INTO business_notification_config (
    tenant_id,
    rubro,
    template_version,
    custom_overrides,
    is_active,
    created_at,
    updated_at
)
SELECT 
    n.id as tenant_id,
    'general' as rubro,
    'latest' as template_version,
    '{}'::jsonb as custom_overrides,
    true as is_active,
    n.fecha_creacion as created_at,
    NOW() as updated_at
FROM negocios n
WHERE NOT EXISTS (
    SELECT 1 FROM business_notification_config bnc 
    WHERE bnc.tenant_id = n.id
)
AND NOT EXISTS (
    SELECT 1 FROM tenant_settings ts 
    WHERE ts.tenant_id = n.id
);

-- PASO 4: MIGRACIÓN DE NOTIFICACIONES EXISTENTES (SI EXISTEN)
-- =====================================================
-- Si hay tabla notifications_old, migrar datos
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'notifications_old') THEN
        INSERT INTO notifications (
            tenant_id,
            user_id,
            template_id,
            title,
            message,
            metadata,
            severity,
            is_read,
            read_at,
            created_at
        )
        SELECT 
            tenant_id,
            user_id,
            template_id,
            title,
            message,
            COALESCE(metadata, '{}'::jsonb),
            COALESCE(severity, 'info'),
            COALESCE(is_read, false),
            read_at,
            created_at
        FROM notifications_old
        WHERE NOT EXISTS (
            SELECT 1 FROM notifications n 
            WHERE n.tenant_id = notifications_old.tenant_id 
              AND n.created_at = notifications_old.created_at
              AND n.title = notifications_old.title
        );
        
        RAISE NOTICE 'Migradas notificaciones existentes desde notifications_old';
    END IF;
END $$;

-- PASO 5: VALIDACIÓN DE MIGRACIÓN
-- =====================================================
-- Verificar que todos los negocios tienen configuración
SELECT 
    'VALIDACIÓN: Negocios con configuración de notificaciones' as status,
    COUNT(DISTINCT n.id) as total_negocios,
    COUNT(DISTINCT bnc.tenant_id) as negocios_con_config,
    COUNT(DISTINCT n.id) - COUNT(DISTINCT bnc.tenant_id) as negocios_sin_config
FROM negocios n
LEFT JOIN business_notification_config bnc ON n.id = bnc.tenant_id;

-- Verificar distribución por rubro
SELECT 
    rubro,
    COUNT(*) as cantidad,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as porcentaje
FROM business_notification_config
GROUP BY rubro
ORDER BY cantidad DESC;

-- PASO 6: LOG DE MIGRACIÓN DE DATOS
-- =====================================================
INSERT INTO migration_log (migration_name, notes) 
VALUES (
    'data_migration_script', 
    CONCAT(
        'Migrados datos existentes al nuevo esquema. ',
        'Configuraciones: ', (SELECT COUNT(*) FROM business_notification_config), ', ',
        'Notificaciones: ', (SELECT COUNT(*) FROM notifications)
    )
);

-- PASO 7: CREAR ÍNDICES PARA PERFORMANCE
-- =====================================================
-- Índices para business_notification_config
CREATE INDEX IF NOT EXISTS idx_business_notification_config_tenant_id 
ON business_notification_config(tenant_id);

CREATE INDEX IF NOT EXISTS idx_business_notification_config_rubro 
ON business_notification_config(rubro);

CREATE INDEX IF NOT EXISTS idx_business_notification_config_active 
ON business_notification_config(is_active) WHERE is_active = true;

-- Índices para notifications
CREATE INDEX IF NOT EXISTS idx_notifications_tenant_id 
ON notifications(tenant_id);

CREATE INDEX IF NOT EXISTS idx_notifications_unread 
ON notifications(tenant_id, is_read, created_at) WHERE is_read = false;

CREATE INDEX IF NOT EXISTS idx_notifications_created_at 
ON notifications(created_at DESC);

RAISE NOTICE 'Migración de datos completada exitosamente';

-- COMENTARIOS IMPORTANTES:
-- ========================
-- 1. Script idempotente - puede ejecutarse múltiples veces sin problemas
-- 2. Preserva datos existentes y los migra al nuevo esquema
-- 3. Crea configuración básica para negocios sin configuración previa
-- 4. Incluye validaciones para verificar integridad
-- 5. Optimiza performance con índices apropiados
