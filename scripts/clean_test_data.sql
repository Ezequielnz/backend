-- Script para limpiar datos de prueba de ventas
-- CUIDADO: Esto eliminará TODAS las ventas y detalles de venta

-- Eliminar todos los detalles de venta
DELETE FROM venta_detalle;

-- Eliminar todas las ventas
DELETE FROM ventas;

-- Reiniciar secuencias si es necesario (opcional)
-- NOTA: En PostgreSQL con UUID no hay secuencias que reiniciar

-- Verificar que las tablas están vacías
SELECT 'ventas' as tabla, COUNT(*) as registros FROM ventas
UNION ALL
SELECT 'venta_detalle' as tabla, COUNT(*) as registros FROM venta_detalle; 