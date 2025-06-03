# 🔧 Guía de Mantenimiento - Sistema de Importación

## 📋 Resumen de Limpieza Automática

El sistema de importación masiva incluye **limpieza automática** de datos temporales para evitar acumulación innecesaria en la base de datos.

## ✅ Limpieza Automática Implementada

### 1. **Limpieza al Confirmar Importación**
- ✅ Se ejecuta automáticamente después de confirmar la importación
- ✅ Elimina todos los datos temporales del usuario para ese negocio
- ✅ También limpia datos antiguos (>24h) de todos los usuarios

### 2. **Limpieza al Cancelar Importación**
- ✅ Se ejecuta automáticamente al cancelar una importación
- ✅ Elimina todos los datos temporales del usuario

### 3. **Limpieza al Iniciar Nueva Importación**
- ✅ Se ejecuta automáticamente antes de procesar un nuevo archivo
- ✅ Limpia importaciones anteriores del mismo usuario

### 4. **Limpieza por Tiempo (24 horas)**
- ✅ Se ejecuta en cada operación de limpieza
- ✅ Elimina automáticamente datos temporales antiguos (>24h)

## 🛠️ Mantenimiento Manual

### Ejecutar Limpieza Manual

```bash
# Desde el directorio backend
python scripts/maintenance.py
```

### Endpoint API para Limpieza

```http
DELETE /api/v1/businesses/{business_id}/import/limpiar-antiguos
Authorization: Bearer {token}
```

## 📊 Tabla de Datos Temporales

**Tabla:** `productos_importacion_temporal`

**Campos principales:**
- `id` - UUID único
- `negocio_id` - ID del negocio
- `usuario_id` - ID del usuario
- `creado_en` - Timestamp de creación
- `estado` - Estado del producto (pendiente, validado, error)

## 🔄 Programar Limpieza Automática (Opcional)

### Usando Cron (Linux/Mac)

```bash
# Ejecutar limpieza diaria a las 2:00 AM
0 2 * * * cd /ruta/a/tu/proyecto/backend && python scripts/maintenance.py
```

### Usando Task Scheduler (Windows)

1. Abrir "Programador de tareas"
2. Crear tarea básica
3. Configurar para ejecutar diariamente
4. Acción: `python scripts/maintenance.py`
5. Directorio: `/ruta/a/tu/proyecto/backend`

## 📈 Monitoreo

### Logs de Limpieza

Los logs se muestran en la consola:

```
🔧 Iniciando mantenimiento completo - 2025-06-03 16:18:25
✅ Limpieza completada: 15 registros eliminados
🎉 Mantenimiento completo finalizado
```

### Verificar Datos Temporales

```sql
-- Contar registros temporales por negocio
SELECT negocio_id, COUNT(*) as total
FROM productos_importacion_temporal 
GROUP BY negocio_id;

-- Ver registros antiguos
SELECT COUNT(*) as registros_antiguos
FROM productos_importacion_temporal 
WHERE creado_en < NOW() - INTERVAL '24 hours';
```

## ⚠️ Consideraciones Importantes

1. **Datos Temporales**: Solo se almacenan durante el proceso de importación
2. **Límite de Tiempo**: 24 horas máximo de retención automática
3. **Seguridad**: RLS implementado - cada usuario solo ve sus datos
4. **Performance**: Índices optimizados para consultas rápidas

## 🚨 Solución de Problemas

### Si hay muchos datos temporales acumulados:

```bash
# Ejecutar limpieza manual
python scripts/maintenance.py
```

### Si el script falla:

1. Verificar conexión a Supabase
2. Verificar permisos de base de datos
3. Revisar logs de error

### Limpieza de emergencia (SQL directo):

```sql
-- ⚠️ SOLO EN EMERGENCIA - Eliminar TODOS los datos temporales
DELETE FROM productos_importacion_temporal 
WHERE creado_en < NOW() - INTERVAL '1 hour';
```

## 📝 Notas de Desarrollo

- **Archivo principal**: `app/services/importacion_productos.py`
- **Tareas**: `app/tasks/maintenance.py`
- **Script**: `scripts/maintenance.py`
- **Endpoint**: `app/api/api_v1/endpoints/importacion.py` 