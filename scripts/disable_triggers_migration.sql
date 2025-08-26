-- =====================================================
-- MIGRACIÓN: DESHABILITAR TRIGGERS Y PASAR A CONTROL FASTAPI
-- =====================================================
-- Fecha: 2025-08-25
-- Objetivo: Eliminar triggers automáticos y migrar a control total desde FastAPI
-- IMPORTANTE: Ejecutar en orden y validar cada paso

-- PASO 1: VERIFICAR TRIGGERS EXISTENTES
-- =====================================================
SELECT 
    schemaname,
    tablename,
    triggername,
    definition
FROM pg_triggers 
WHERE triggername LIKE '%notification%' 
   OR triggername LIKE '%copy%template%'
   OR definition ILIKE '%notification%'
ORDER BY schemaname, tablename, triggername;

-- PASO 2: DESHABILITAR TRIGGERS HEREDADOS (SI EXISTEN)
-- =====================================================
-- Trigger principal que podría copiar templates automáticamente
DROP TRIGGER IF EXISTS copy_notification_templates ON tenant_settings;
DROP TRIGGER IF EXISTS auto_create_notification_config ON tenant_settings;
DROP TRIGGER IF EXISTS initialize_business_notifications ON negocios;

-- Triggers relacionados con notificaciones automáticas
DROP TRIGGER IF EXISTS notification_rule_update ON notification_rules;
DROP TRIGGER IF EXISTS notification_template_sync ON notification_templates;

-- PASO 3: ELIMINAR FUNCIONES DE TRIGGER (SI EXISTEN)
-- =====================================================
DROP FUNCTION IF EXISTS copy_notification_templates_fn();
DROP FUNCTION IF EXISTS auto_create_notification_config_fn();
DROP FUNCTION IF EXISTS initialize_business_notifications_fn();
DROP FUNCTION IF EXISTS sync_notification_templates_fn();

-- PASO 4: VERIFICAR QUE NO QUEDAN TRIGGERS ACTIVOS
-- =====================================================
SELECT 
    'VERIFICACIÓN: Triggers restantes relacionados con notificaciones' as status,
    COUNT(*) as trigger_count
FROM pg_triggers 
WHERE triggername LIKE '%notification%' 
   OR triggername LIKE '%copy%template%'
   OR definition ILIKE '%notification%';

-- PASO 5: CREAR LOG DE MIGRACIÓN
-- =====================================================
DO $$
BEGIN
    -- Crear tabla de log si no existe
    CREATE TABLE IF NOT EXISTS migration_log (
        id SERIAL PRIMARY KEY,
        migration_name VARCHAR(255) NOT NULL,
        executed_at TIMESTAMP DEFAULT NOW(),
        status VARCHAR(50) DEFAULT 'completed',
        notes TEXT
    );
    
    -- Registrar esta migración
    INSERT INTO migration_log (migration_name, notes) 
    VALUES (
        'disable_triggers_migration', 
        'Deshabilitados triggers automáticos de notificaciones. Control transferido a FastAPI.'
    );
    
    RAISE NOTICE 'Migración completada: Triggers deshabilitados exitosamente';
END $$;

-- PASO 6: VALIDACIÓN FINAL
-- =====================================================
-- Verificar que las tablas principales existen para el nuevo sistema
SELECT 
    table_name,
    CASE 
        WHEN table_name IN (
            'tenant_settings', 
            'notification_rule_templates', 
            'business_notification_config',
            'notification_templates',
            'notifications'
        ) THEN 'REQUERIDA'
        ELSE 'OPCIONAL'
    END as importance
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name LIKE '%notification%'
  OR table_name = 'tenant_settings'
ORDER BY importance DESC, table_name;

-- COMENTARIOS IMPORTANTES:
-- ========================
-- 1. Este script es SEGURO - solo elimina triggers, no datos
-- 2. Si no hay triggers, las operaciones DROP IF EXISTS no fallan
-- 3. El control pasa completamente a FastAPI vía NotificationConfigService
-- 4. Se mantiene compatibilidad con datos existentes
-- 5. Log de migración para auditoría
