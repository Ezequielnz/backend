-- Script para corregir las políticas RLS de las tablas de ventas
-- Problema: Las políticas actuales usan "negocio_usuarios" en lugar de "usuarios_negocios"

-- Eliminar políticas existentes para la tabla ventas
DROP POLICY IF EXISTS "Users can view sales from their businesses" ON ventas;
DROP POLICY IF EXISTS "Users can create sales in their businesses" ON ventas;
DROP POLICY IF EXISTS "Users can update sales from their businesses" ON ventas;
DROP POLICY IF EXISTS "Users can delete sales from their businesses" ON ventas;

-- Recrear políticas con el nombre correcto de tabla (usuarios_negocios)
-- Los usuarios pueden ver ventas de sus negocios
CREATE POLICY "Users can view sales from their businesses" ON ventas
    FOR SELECT USING (
        negocio_id IN (
            SELECT un.negocio_id 
            FROM usuarios_negocios un 
            WHERE un.usuario_id = auth.uid()
        )
    );

-- Los usuarios pueden crear ventas en sus negocios
CREATE POLICY "Users can create sales in their businesses" ON ventas
    FOR INSERT WITH CHECK (
        negocio_id IN (
            SELECT un.negocio_id 
            FROM usuarios_negocios un 
            WHERE un.usuario_id = auth.uid()
        )
    );

-- Los usuarios pueden actualizar ventas de sus negocios
CREATE POLICY "Users can update sales from their businesses" ON ventas
    FOR UPDATE USING (
        negocio_id IN (
            SELECT un.negocio_id 
            FROM usuarios_negocios un 
            WHERE un.usuario_id = auth.uid()
        )
    );

-- Los usuarios pueden eliminar ventas de sus negocios
CREATE POLICY "Users can delete sales from their businesses" ON ventas
    FOR DELETE USING (
        negocio_id IN (
            SELECT un.negocio_id 
            FROM usuarios_negocios un 
            WHERE un.usuario_id = auth.uid()
        )
    );

-- Eliminar políticas existentes para la tabla venta_detalle
DROP POLICY IF EXISTS "Users can view sale details from their businesses" ON venta_detalle;
DROP POLICY IF EXISTS "Users can create sale details in their businesses" ON venta_detalle;
DROP POLICY IF EXISTS "Users can update sale details from their businesses" ON venta_detalle;
DROP POLICY IF EXISTS "Users can delete sale details from their businesses" ON venta_detalle;

-- Recrear políticas con el nombre correcto de tabla (usuarios_negocios)
-- Los usuarios pueden ver detalles de ventas de sus negocios
CREATE POLICY "Users can view sale details from their businesses" ON venta_detalle
    FOR SELECT USING (
        venta_id IN (
            SELECT v.id 
            FROM ventas v 
            WHERE v.negocio_id IN (
                SELECT un.negocio_id 
                FROM usuarios_negocios un 
                WHERE un.usuario_id = auth.uid()
            )
        )
    );

-- Los usuarios pueden crear detalles de ventas en sus negocios
CREATE POLICY "Users can create sale details in their businesses" ON venta_detalle
    FOR INSERT WITH CHECK (
        venta_id IN (
            SELECT v.id 
            FROM ventas v 
            WHERE v.negocio_id IN (
                SELECT un.negocio_id 
                FROM usuarios_negocios un 
                WHERE un.usuario_id = auth.uid()
            )
        )
    );

-- Los usuarios pueden actualizar detalles de ventas de sus negocios
CREATE POLICY "Users can update sale details from their businesses" ON venta_detalle
    FOR UPDATE USING (
        venta_id IN (
            SELECT v.id 
            FROM ventas v 
            WHERE v.negocio_id IN (
                SELECT un.negocio_id 
                FROM usuarios_negocios un 
                WHERE un.usuario_id = auth.uid()
            )
        )
    );

-- Los usuarios pueden eliminar detalles de ventas de sus negocios
CREATE POLICY "Users can delete sale details from their businesses" ON venta_detalle
    FOR DELETE USING (
        venta_id IN (
            SELECT v.id 
            FROM ventas v 
            WHERE v.negocio_id IN (
                SELECT un.negocio_id 
                FROM usuarios_negocios un 
                WHERE un.usuario_id = auth.uid()
            )
        )
    );

-- Confirmar que se han recreado las políticas
DO $$
BEGIN
    RAISE NOTICE 'Políticas RLS de ventas actualizadas correctamente';
END $$;
