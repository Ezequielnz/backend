-- Script para corregir constraints únicos problemáticos en la tabla ventas
-- Estos constraints impiden que un negocio tenga múltiples ventas

-- Verificar constraints existentes
SELECT constraint_name, constraint_type 
FROM information_schema.table_constraints 
WHERE table_name = 'ventas' AND constraint_type = 'UNIQUE';

-- Eliminar constraint único en negocio_id (permite múltiples ventas por negocio)
ALTER TABLE ventas DROP CONSTRAINT IF EXISTS ventas_negocio_id_key;

-- Eliminar constraint único en usuario_negocio_id si existe
ALTER TABLE ventas DROP CONSTRAINT IF EXISTS ventas_usuario_negocio_id_key;

-- Verificar que los constraints se eliminaron
SELECT constraint_name, constraint_type 
FROM information_schema.table_constraints 
WHERE table_name = 'ventas' AND constraint_type = 'UNIQUE';

-- Limpiar datos de prueba existentes
DELETE FROM venta_detalle;
DELETE FROM ventas;

-- Verificar que las tablas están limpias
SELECT 'ventas' as tabla, COUNT(*) as registros FROM ventas
UNION ALL
SELECT 'venta_detalle' as tabla, COUNT(*) as registros FROM venta_detalle; 