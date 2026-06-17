-- Renombrar nombre a razon_social en proveedores
ALTER TABLE proveedores RENAME COLUMN nombre TO razon_social;

-- Renombrar cuit_cuil a documento_numero
ALTER TABLE proveedores RENAME COLUMN cuit_cuil TO documento_numero;

-- Agregar documento_tipo
ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS documento_tipo VARCHAR(20) DEFAULT 'CUIT';
