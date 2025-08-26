-- =====================================================
-- PLAN DE ROLLBACK: SISTEMA DE NOTIFICACIONES
-- =====================================================
-- Fecha: 2025-08-25
-- Objetivo: Plan completo de rollback en caso de problemas
-- IMPORTANTE: Ejecutar solo si la migración falla o causa problemas

-- PASO 1: CREAR SNAPSHOT ANTES DE LA MIGRACIÓN
-- =====================================================
-- Ejecutar ANTES de cualquier migración

-- Backup de tenant_settings
CREATE TABLE IF NOT EXISTS tenant_settings_backup AS 
SELECT * FROM tenant_settings;

-- Backup de notificaciones existentes (si existen)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'notifications') THEN
        EXECUTE 'CREATE TABLE notifications_backup AS SELECT * FROM notifications';
    END IF;
END $$;

-- Backup de configuraciones existentes
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'notification_rules') THEN
        EXECUTE 'CREATE TABLE notification_rules_backup AS SELECT * FROM notification_rules';
    END IF;
END $$;

-- Log del snapshot
INSERT INTO migration_log (migration_name, status, notes) 
VALUES (
    'pre_migration_snapshot', 
    'backup_created',
    CONCAT(
        'Snapshot creado antes de migración. ',
        'tenant_settings: ', (SELECT COUNT(*) FROM tenant_settings_backup), ' registros'
    )
);

-- PASO 2: ROLLBACK COMPLETO (SOLO SI ES NECESARIO)
-- =====================================================
-- ADVERTENCIA: Esto revierte TODOS los cambios

-- Eliminar nuevas tablas creadas
DROP TABLE IF EXISTS business_notification_config CASCADE;
DROP TABLE IF EXISTS notification_rule_templates CASCADE;
DROP TABLE IF EXISTS notification_templates CASCADE;
DROP TABLE IF EXISTS notifications CASCADE;
DROP TABLE IF EXISTS notification_audit_log CASCADE;
DROP TABLE IF EXISTS ml_features CASCADE;
DROP TABLE IF EXISTS ml_models CASCADE;
DROP TABLE IF EXISTS ml_predictions CASCADE;

-- Restaurar tenant_settings desde backup
TRUNCATE TABLE tenant_settings;
INSERT INTO tenant_settings SELECT * FROM tenant_settings_backup;

-- Restaurar notificaciones desde backup (si existían)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'notifications_backup') THEN
        EXECUTE 'CREATE TABLE notifications AS SELECT * FROM notifications_backup';
    END IF;
END $$;

-- PASO 3: ROLLBACK PARCIAL - SOLO DESHABILITAR NUEVAS FUNCIONALIDADES
-- =====================================================
-- Opción más segura: mantener datos pero deshabilitar funcionalidades

-- Deshabilitar todas las configuraciones de notificaciones
UPDATE business_notification_config SET is_active = false;

-- Marcar templates como inactivos
UPDATE notification_rule_templates SET is_latest = false;

-- PASO 4: RECREAR TRIGGERS ANTIGUOS (SI EXISTÍAN)
-- =====================================================
-- Solo si había triggers previos que necesitan restaurarse

-- Ejemplo de trigger que podría necesitar restauración:
/*
CREATE OR REPLACE FUNCTION copy_notification_templates_fn()
RETURNS TRIGGER AS $$
BEGIN
    -- Lógica del trigger anterior (si existía)
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER copy_notification_templates
    AFTER INSERT ON tenant_settings
    FOR EACH ROW
    EXECUTE FUNCTION copy_notification_templates_fn();
*/

-- PASO 5: VALIDACIÓN POST-ROLLBACK
-- =====================================================
-- Verificar que el sistema volvió al estado anterior

SELECT 
    'POST-ROLLBACK: Estado de tablas' as status,
    COUNT(*) as tenant_settings_count
FROM tenant_settings;

-- Verificar que no hay triggers nuevos activos
SELECT 
    'POST-ROLLBACK: Triggers activos' as status,
    COUNT(*) as trigger_count
FROM pg_triggers 
WHERE triggername LIKE '%notification%';

-- PASO 6: LIMPIEZA DE BACKUPS (OPCIONAL)
-- =====================================================
-- Ejecutar solo después de confirmar que todo funciona correctamente

-- DROP TABLE IF EXISTS tenant_settings_backup;
-- DROP TABLE IF EXISTS notifications_backup;
-- DROP TABLE IF EXISTS notification_rules_backup;

-- PASO 7: LOG DE ROLLBACK
-- =====================================================
INSERT INTO migration_log (migration_name, status, notes) 
VALUES (
    'rollback_executed', 
    'completed',
    'Rollback ejecutado. Sistema restaurado al estado anterior.'
);

-- =====================================================
-- INSTRUCCIONES DE USO DEL ROLLBACK
-- =====================================================

/*
ANTES DE LA MIGRACIÓN:
1. Ejecutar solo PASO 1 para crear snapshot
2. Verificar que los backups se crearon correctamente

EN CASO DE PROBLEMAS:
1. Evaluar si necesita rollback completo (PASO 2) o parcial (PASO 3)
2. Rollback completo: elimina todas las nuevas tablas y restaura estado anterior
3. Rollback parcial: mantiene datos pero deshabilita funcionalidades

DESPUÉS DEL ROLLBACK:
1. Ejecutar PASO 5 para validar
2. Revisar logs de aplicación para confirmar funcionamiento
3. Una vez confirmado, ejecutar PASO 6 para limpiar backups

NOTAS IMPORTANTES:
- El rollback completo elimina TODOS los datos de notificaciones nuevos
- El rollback parcial es más seguro pero mantiene las tablas
- Siempre validar en ambiente de desarrollo primero
- Tener plan de comunicación con usuarios en caso de downtime
*/
