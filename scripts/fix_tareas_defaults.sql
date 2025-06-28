-- Script para arreglar los valores por defecto problemáticos en la tabla tareas
-- Estos valores por defecto gen_random_uuid() causan errores de foreign key
-- porque generan UUIDs que no existen en las tablas referenciadas

-- Eliminar valores por defecto problemáticos
ALTER TABLE tareas ALTER COLUMN asignada_a_id DROP DEFAULT;
ALTER TABLE tareas ALTER COLUMN creada_por_id DROP DEFAULT;

-- Verificar que los cambios se aplicaron correctamente
SELECT 
    column_name,
    column_default,
    is_nullable
FROM information_schema.columns 
WHERE table_name = 'tareas' 
AND table_schema = 'public'
AND column_name IN ('asignada_a_id', 'creada_por_id')
ORDER BY column_name; 