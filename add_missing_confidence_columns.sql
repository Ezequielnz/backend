-- Migración para agregar columnas de confianza faltantes
-- Ejecutar en Supabase SQL Editor

-- Agregar columnas de confianza que faltan
ALTER TABLE productos_importacion_temporal 
ADD COLUMN IF NOT EXISTS confianza_descripcion DECIMAL(3,2) DEFAULT 0.0;

ALTER TABLE productos_importacion_temporal 
ADD COLUMN IF NOT EXISTS confianza_categoria DECIMAL(3,2) DEFAULT 0.0;

ALTER TABLE productos_importacion_temporal 
ADD COLUMN IF NOT EXISTS confianza_stock_minimo DECIMAL(3,2) DEFAULT 0.0;

-- Verificar que todas las columnas de confianza existan
-- (Las siguientes ya deberían existir, pero las agregamos por seguridad)
ALTER TABLE productos_importacion_temporal 
ADD COLUMN IF NOT EXISTS confianza_nombre DECIMAL(3,2) DEFAULT 0.0;

ALTER TABLE productos_importacion_temporal 
ADD COLUMN IF NOT EXISTS confianza_precio_venta DECIMAL(3,2) DEFAULT 0.0;

ALTER TABLE productos_importacion_temporal 
ADD COLUMN IF NOT EXISTS confianza_precio_compra DECIMAL(3,2) DEFAULT 0.0;

ALTER TABLE productos_importacion_temporal 
ADD COLUMN IF NOT EXISTS confianza_stock_actual DECIMAL(3,2) DEFAULT 0.0;

ALTER TABLE productos_importacion_temporal 
ADD COLUMN IF NOT EXISTS confianza_codigo DECIMAL(3,2) DEFAULT 0.0;

-- Comentario para verificación
COMMENT ON COLUMN productos_importacion_temporal.confianza_descripcion IS 'Confianza del reconocimiento de la columna descripción (0.0-1.0)';
COMMENT ON COLUMN productos_importacion_temporal.confianza_categoria IS 'Confianza del reconocimiento de la columna categoría (0.0-1.0)';
COMMENT ON COLUMN productos_importacion_temporal.confianza_stock_minimo IS 'Confianza del reconocimiento de la columna stock mínimo (0.0-1.0)';

-- Verificar estructura final
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns 
WHERE table_name = 'productos_importacion_temporal' 
  AND column_name LIKE 'confianza_%'
ORDER BY column_name; 