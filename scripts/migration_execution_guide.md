# Guía de Ejecución de Migración - Sistema de Notificaciones

## Orden de Ejecución (CRÍTICO)

### 1. Pre-Migración (OBLIGATORIO)
```sql
-- Ejecutar SOLO el PASO 1 de rollback_plan.sql
-- Esto crea los snapshots de seguridad
```

### 2. Deshabilitar Triggers
```sql
-- Ejecutar disable_triggers_migration.sql completo
-- Verifica que no quedan triggers activos
```

### 3. Crear Tablas Nuevas
```sql
-- Ejecutar create_notifications_ml_tables.sql completo
-- Crea toda la estructura del nuevo sistema
```

### 4. Migrar Datos Existentes
```sql
-- Ejecutar data_migration_script.sql completo
-- Migra configuraciones existentes sin pérdida de datos
```

## Validaciones Entre Pasos

### Después del Paso 2:
```sql
SELECT COUNT(*) FROM pg_triggers WHERE triggername LIKE '%notification%';
-- Debe retornar 0
```

### Después del Paso 3:
```sql
SELECT table_name FROM information_schema.tables 
WHERE table_name IN ('business_notification_config', 'notification_rule_templates');
-- Debe mostrar ambas tablas
```

### Después del Paso 4:
```sql
SELECT COUNT(*) FROM business_notification_config;
-- Debe mostrar configuraciones migradas
```

## En Caso de Error

1. **NO CONTINUAR** con pasos siguientes
2. Ejecutar rollback apropiado desde `rollback_plan.sql`
3. Investigar causa del error
4. Corregir y reintentar desde el paso que falló

## Verificación Final

```sql
-- Todos los negocios tienen configuración
SELECT 
    (SELECT COUNT(*) FROM negocios) as total_negocios,
    (SELECT COUNT(*) FROM business_notification_config) as configuraciones;

-- No hay triggers activos
SELECT COUNT(*) FROM pg_triggers WHERE triggername LIKE '%notification%';
```

## Estado Objetivo

✅ **Triggers eliminados**: Control 100% desde FastAPI  
✅ **Datos migrados**: Sin pérdida de configuraciones existentes  
✅ **Sistema funcional**: API endpoints operativos  
✅ **Rollback disponible**: Plan de contingencia listo
