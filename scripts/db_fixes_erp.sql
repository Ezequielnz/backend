-- 1. Agregar condicion_iva a proveedores para mantener consistencia con clientes
ALTER TABLE proveedores
ADD COLUMN IF NOT EXISTS condicion_iva VARCHAR(100);

-- 2. Asegurar que las referencias a proveedores no impidan su eliminación
-- Para productos
ALTER TABLE productos 
DROP CONSTRAINT IF EXISTS productos_proveedor_id_fkey,
ADD CONSTRAINT productos_proveedor_id_fkey 
FOREIGN KEY (proveedor_id) 
REFERENCES proveedores(id) 
ON DELETE SET NULL;

-- Para compras
ALTER TABLE compras
DROP CONSTRAINT IF EXISTS compras_proveedor_id_fkey,
ADD CONSTRAINT compras_proveedor_id_fkey
FOREIGN KEY (proveedor_id)
REFERENCES proveedores(id)
ON DELETE SET NULL;
