-- Script para agregar columnas faltantes en permisos_usuario_negocio
-- Fecha: 2024
-- Descripción: Agrega la columna puede_eliminar_ventas que falta en la tabla

-- Agregar columna faltante para permisos de eliminación de ventas
ALTER TABLE permisos_usuario_negocio 
ADD COLUMN IF NOT EXISTS puede_eliminar_ventas boolean DEFAULT false;

-- Comentario para documentar la nueva columna
COMMENT ON COLUMN permisos_usuario_negocio.puede_eliminar_ventas IS 'Permite al usuario eliminar ventas del sistema POS';

-- Verificar que la columna se agregó correctamente
SELECT column_name, data_type, is_nullable, column_default 
FROM information_schema.columns 
WHERE table_name = 'permisos_usuario_negocio' 
AND column_name = 'puede_eliminar_ventas'; 