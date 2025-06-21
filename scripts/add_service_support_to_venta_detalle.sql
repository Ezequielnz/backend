-- Migración para agregar soporte de servicios en venta_detalle
-- 
-- PROBLEMA: La tabla venta_detalle solo maneja productos, pero necesitamos
-- que también maneje servicios para el POS.
--
-- SOLUCIÓN: Agregar campos para servicios y hacer los campos opcionales

-- 1. Agregar campo para servicios
ALTER TABLE venta_detalle 
ADD COLUMN servicio_id UUID REFERENCES servicios(id);

-- 2. Agregar campo tipo para distinguir entre producto y servicio
ALTER TABLE venta_detalle 
ADD COLUMN tipo VARCHAR(20) DEFAULT 'producto' CHECK (tipo IN ('producto', 'servicio'));

-- 3. Hacer producto_id opcional (puede ser NULL si es un servicio)
ALTER TABLE venta_detalle 
ALTER COLUMN producto_id DROP NOT NULL;

-- 4. Agregar restricción para asegurar que solo uno de producto_id o servicio_id sea NOT NULL
ALTER TABLE venta_detalle 
ADD CONSTRAINT venta_detalle_producto_or_servicio_check 
CHECK (
  (producto_id IS NOT NULL AND servicio_id IS NULL AND tipo = 'producto') OR
  (producto_id IS NULL AND servicio_id IS NOT NULL AND tipo = 'servicio')
);

-- 5. Crear índices para mejorar performance
CREATE INDEX idx_venta_detalle_servicio_id ON venta_detalle(servicio_id);
CREATE INDEX idx_venta_detalle_tipo ON venta_detalle(tipo);

-- 6. Verificar que la migración se aplicó correctamente
SELECT 
    column_name, 
    data_type, 
    is_nullable,
    column_default
FROM information_schema.columns 
WHERE table_name = 'venta_detalle' 
ORDER BY ordinal_position; 