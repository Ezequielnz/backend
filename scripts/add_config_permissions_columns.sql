-- =====================================================
-- MIGRACIÓN: Agregar permisos de configuración a permisos_usuario_negocio
-- =====================================================
-- Fecha: 2025-08-28
-- Descripción: Agrega las columnas booleanas para controlar acceso a Configuración
--              relacionadas a las reglas de notificaciones u otras configuraciones.
--              Se crean con DEFAULT false y se normalizan nulos existentes.

-- Agregar columna para ver configuración
ALTER TABLE permisos_usuario_negocio 
ADD COLUMN IF NOT EXISTS puede_ver_configuracion boolean DEFAULT false;

COMMENT ON COLUMN permisos_usuario_negocio.puede_ver_configuracion IS 
  'Permite ver la configuración del negocio (incluye reglas de notificaciones)';

-- Agregar columna para editar configuración
ALTER TABLE permisos_usuario_negocio 
ADD COLUMN IF NOT EXISTS puede_editar_configuracion boolean DEFAULT false;

COMMENT ON COLUMN permisos_usuario_negocio.puede_editar_configuracion IS 
  'Permite editar/administrar la configuración del negocio (incluye reglas de notificaciones)';

-- Normalizar nulos (por si la base tenía filas existentes antes del DEFAULT)
UPDATE permisos_usuario_negocio
SET 
  puede_ver_configuracion = COALESCE(puede_ver_configuracion, false),
  puede_editar_configuracion = COALESCE(puede_editar_configuracion, false)
WHERE puede_ver_configuracion IS NULL
   OR puede_editar_configuracion IS NULL;

-- Validación rápida de columnas
SELECT column_name, data_type, is_nullable, column_default 
FROM information_schema.columns 
WHERE table_name = 'permisos_usuario_negocio' 
  AND column_name IN ('puede_ver_configuracion', 'puede_editar_configuracion');
