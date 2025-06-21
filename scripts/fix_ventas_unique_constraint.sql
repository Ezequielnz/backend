-- Script para eliminar la restricción de unicidad incorrecta en la tabla ventas
-- 
-- PROBLEMA: La restricción 'ventas_empleado_id_key' hace que el campo 'usuario_negocio_id' 
-- sea único, lo que impide que un usuario pueda crear múltiples ventas.
--
-- SOLUCIÓN: Eliminar esta restricción para permitir múltiples ventas por usuario.

-- Eliminar la restricción de unicidad incorrecta
ALTER TABLE ventas DROP CONSTRAINT IF EXISTS ventas_empleado_id_key;

-- Verificar que la restricción se eliminó correctamente
SELECT 
    conname as constraint_name,
    contype as constraint_type,
    pg_get_constraintdef(c.oid) as constraint_definition
FROM pg_constraint c
JOIN pg_class t ON c.conrelid = t.oid
JOIN pg_namespace n ON t.relnamespace = n.oid
WHERE t.relname = 'ventas' 
    AND n.nspname = 'public'
    AND contype IN ('u', 'p'); 