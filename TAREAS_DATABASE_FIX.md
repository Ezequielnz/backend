# Fix para la Tabla de Tareas - Problema de Valores por Defecto

## 🔍 Problema Identificado

La tabla `tareas` en Supabase tiene valores por defecto problemáticos que causan errores 422 al crear tareas:

```sql
-- Campos problemáticos:
asignada_a_id uuid DEFAULT gen_random_uuid()
creada_por_id uuid DEFAULT gen_random_uuid()
```

## ❌ Por qué causa errores

1. **Foreign Key Constraints**: Estos campos tienen restricciones de foreign key:
   - `asignada_a_id` → `usuarios_negocios(id)`
   - `creada_por_id` → `usuarios_negocios(id)`

2. **UUIDs Aleatorios**: `gen_random_uuid()` genera UUIDs que no existen en las tablas referenciadas

3. **Error 422**: Cuando se intenta insertar, las foreign keys fallan porque los UUIDs generados no son válidos

## ✅ Solución

### 1. Ejecutar Script SQL (REQUERIDO)

```sql
-- Eliminar valores por defecto problemáticos
ALTER TABLE tareas ALTER COLUMN asignada_a_id DROP DEFAULT;
ALTER TABLE tareas ALTER COLUMN creada_por_id DROP DEFAULT;
```

### 2. Cambios en el Backend (YA IMPLEMENTADOS)

- ✅ Eliminado `negocio_id` del schema `TareaCreate`
- ✅ Agregado manejo explícito de `asignada_a_id` como NULL
- ✅ Agregado logging para debugging
- ✅ Mejorado manejo de errores

### 3. Cambios en el Frontend (YA IMPLEMENTADOS)

- ✅ Campos de fecha cambiados a `datetime-local`
- ✅ Conversión correcta de fechas a formato ISO
- ✅ Validación de datos antes del envío
- ✅ Manejo robusto de errores

## 🔄 Estado Actual

- **Backend**: ✅ Preparado para manejar los datos correctamente
- **Frontend**: ✅ Envía datos en formato correcto
- **Base de Datos**: ❌ **REQUIERE EJECUTAR EL SCRIPT SQL**

## 📋 Para Completar la Solución

1. Ejecutar el script SQL en Supabase:
   ```bash
   # En Supabase SQL Editor
   ALTER TABLE tareas ALTER COLUMN asignada_a_id DROP DEFAULT;
   ALTER TABLE tareas ALTER COLUMN creada_por_id DROP DEFAULT;
   ```

2. Verificar que funciona creando una tarea de prueba

## 🎯 Resultado Esperado

Una vez ejecutado el script SQL, deberías poder crear múltiples tareas sin errores 422. 