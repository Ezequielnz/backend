-- Script para corregir el campo usuario_negocio_id en la tabla ventas
-- Hacer el campo opcional en lugar de obligatorio

-- Verificar la estructura actual de la tabla ventas
SELECT column_name, is_nullable, data_type 
FROM information_schema.columns 
WHERE table_name = 'ventas' AND column_name = 'usuario_negocio_id';

-- Hacer el campo usuario_negocio_id opcional (permitir NULL)
ALTER TABLE ventas ALTER COLUMN usuario_negocio_id DROP NOT NULL;

-- Verificar que el cambio se aplicó
SELECT column_name, is_nullable, data_type 
FROM information_schema.columns 
WHERE table_name = 'ventas' AND column_name = 'usuario_negocio_id';

-- Limpiar datos de prueba existentes (opcional)
DELETE FROM venta_detalle;
DELETE FROM ventas; 