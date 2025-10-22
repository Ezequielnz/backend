-- =====================================================
-- Migration 04: Add Foreign Key Constraints
-- =====================================================
-- Description: Adds all foreign key constraints for negocio_id and sucursal_id
-- Author: Database Migration Script
-- Date: 2025-01-20
-- =====================================================

-- =====================================================
-- SECTION 1: Foreign Keys to negocios table
-- =====================================================

-- usuarios.negocio_id -> negocios.id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_usuarios_negocio_id' 
        AND table_name = 'usuarios'
    ) THEN
        ALTER TABLE public.usuarios 
        ADD CONSTRAINT fk_usuarios_negocio_id 
        FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added FK: usuarios.negocio_id -> negocios.id';
    END IF;
END $$;

-- productos.negocio_id -> negocios.id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_productos_negocio_id' 
        AND table_name = 'productos'
    ) THEN
        ALTER TABLE public.productos 
        ADD CONSTRAINT fk_productos_negocio_id 
        FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added FK: productos.negocio_id -> negocios.id';
    END IF;
END $$;

-- clientes.negocio_id -> negocios.id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_clientes_negocio_id' 
        AND table_name = 'clientes'
    ) THEN
        ALTER TABLE public.clientes 
        ADD CONSTRAINT fk_clientes_negocio_id 
        FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added FK: clientes.negocio_id -> negocios.id';
    END IF;
END $$;

-- proveedores.negocio_id -> negocios.id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_proveedores_negocio_id' 
        AND table_name = 'proveedores'
    ) THEN
        ALTER TABLE public.proveedores 
        ADD CONSTRAINT fk_proveedores_negocio_id 
        FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added FK: proveedores.negocio_id -> negocios.id';
    END IF;
END $$;

-- ventas.negocio_id -> negocios.id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_ventas_negocio_id' 
        AND table_name = 'ventas'
    ) THEN
        ALTER TABLE public.ventas 
        ADD CONSTRAINT fk_ventas_negocio_id 
        FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added FK: ventas.negocio_id -> negocios.id';
    END IF;
END $$;

-- compras.negocio_id -> negocios.id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_compras_negocio_id' 
        AND table_name = 'compras'
    ) THEN
        ALTER TABLE public.compras 
        ADD CONSTRAINT fk_compras_negocio_id 
        FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added FK: compras.negocio_id -> negocios.id';
    END IF;
END $$;

-- inventario_sucursal.negocio_id -> negocios.id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'inventario_sucursal'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE constraint_name = 'fk_inventario_sucursal_negocio_id' 
            AND table_name = 'inventario_sucursal'
        ) THEN
            ALTER TABLE public.inventario_sucursal 
            ADD CONSTRAINT fk_inventario_sucursal_negocio_id 
            FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;
            RAISE NOTICE 'Added FK: inventario_sucursal.negocio_id -> negocios.id';
        END IF;
    ELSE
        RAISE NOTICE 'Skipped FK for inventario_sucursal (table not found)';
    END IF;
END $$;

-- audit_log.negocio_id -> negocios.id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'audit_log'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE constraint_name = 'fk_audit_log_negocio_id' 
            AND table_name = 'audit_log'
        ) THEN
            ALTER TABLE public.audit_log 
            ADD CONSTRAINT fk_audit_log_negocio_id 
            FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;
            RAISE NOTICE 'Added FK: audit_log.negocio_id -> negocios.id';
        END IF;
    ELSE
        RAISE NOTICE 'Skipped FK: audit_log.negocio_id (table not found)';
    END IF;
END $$;

-- eventos.negocio_id -> negocios.id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'eventos'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE constraint_name = 'fk_eventos_negocio_id' 
            AND table_name = 'eventos'
        ) THEN
            ALTER TABLE public.eventos 
            ADD CONSTRAINT fk_eventos_negocio_id 
            FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;
            RAISE NOTICE 'Added FK: eventos.negocio_id -> negocios.id';
        END IF;
    ELSE
        RAISE NOTICE 'Skipped FK: eventos.negocio_id (table not found)';
    END IF;
END $$;

-- notificaciones.negocio_id -> negocios.id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'notificaciones'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE constraint_name = 'fk_notificaciones_negocio_id' 
            AND table_name = 'notificaciones'
        ) THEN
            ALTER TABLE public.notificaciones 
            ADD CONSTRAINT fk_notificaciones_negocio_id 
            FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;
            RAISE NOTICE 'Added FK: notificaciones.negocio_id -> negocios.id';
        END IF;
    ELSE
        RAISE NOTICE 'Skipped FK: notificaciones.negocio_id (table not found)';
    END IF;
END $$;

-- transferencias_stock.negocio_id -> negocios.id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'transferencias_stock'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE constraint_name = 'fk_transferencias_stock_negocio_id' 
            AND table_name = 'transferencias_stock'
        ) THEN
            ALTER TABLE public.transferencias_stock 
            ADD CONSTRAINT fk_transferencias_stock_negocio_id 
            FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;
            RAISE NOTICE 'Added FK: transferencias_stock.negocio_id -> negocios.id';
        END IF;
    ELSE
        RAISE NOTICE 'Skipped FK: transferencias_stock.negocio_id (table not found)';
    END IF;
END $$;

-- venta_detalle.negocio_id -> negocios.id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_venta_detalle_negocio_id' 
        AND table_name = 'venta_detalle'
    ) THEN
        ALTER TABLE public.venta_detalle 
        ADD CONSTRAINT fk_venta_detalle_negocio_id 
        FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added FK: venta_detalle.negocio_id -> negocios.id';
    END IF;
END $$;

-- compras_detalle.negocio_id -> negocios.id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_compras_detalle_negocio_id' 
        AND table_name = 'compras_detalle'
    ) THEN
        ALTER TABLE public.compras_detalle 
        ADD CONSTRAINT fk_compras_detalle_negocio_id 
        FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added FK: compras_detalle.negocio_id -> negocios.id';
    END IF;
END $$;

-- =====================================================
-- SECTION 2: Foreign Keys to sucursales table
-- =====================================================

-- usuarios.sucursal_id -> sucursales.id (optional default branch)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_usuarios_sucursal_id' 
        AND table_name = 'usuarios'
    ) THEN
        ALTER TABLE public.usuarios 
        ADD CONSTRAINT fk_usuarios_sucursal_id 
        FOREIGN KEY (sucursal_id) REFERENCES public.sucursales(id) ON DELETE SET NULL;
        RAISE NOTICE 'Added FK: usuarios.sucursal_id -> sucursales.id';
    END IF;
END $$;

-- ventas.sucursal_id -> sucursales.id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_ventas_sucursal_id' 
        AND table_name = 'ventas'
    ) THEN
        ALTER TABLE public.ventas 
        ADD CONSTRAINT fk_ventas_sucursal_id 
        FOREIGN KEY (sucursal_id) REFERENCES public.sucursales(id) ON DELETE RESTRICT;
        RAISE NOTICE 'Added FK: ventas.sucursal_id -> sucursales.id';
    END IF;
END $$;

-- compras.sucursal_id -> sucursales.id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_compras_sucursal_id' 
        AND table_name = 'compras'
    ) THEN
        ALTER TABLE public.compras 
        ADD CONSTRAINT fk_compras_sucursal_id 
        FOREIGN KEY (sucursal_id) REFERENCES public.sucursales(id) ON DELETE RESTRICT;
        RAISE NOTICE 'Added FK: compras.sucursal_id -> sucursales.id';
    END IF;
END $$;

-- inventario_sucursal.sucursal_id -> sucursales.id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'inventario_sucursal'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE constraint_name = 'fk_inventario_sucursal_sucursal_id' 
            AND table_name = 'inventario_sucursal'
        ) THEN
            ALTER TABLE public.inventario_sucursal 
            ADD CONSTRAINT fk_inventario_sucursal_sucursal_id 
            FOREIGN KEY (sucursal_id) REFERENCES public.sucursales(id) ON DELETE CASCADE;
            RAISE NOTICE 'Added FK: inventario_sucursal.sucursal_id -> sucursales.id';
        END IF;
    ELSE
        RAISE NOTICE 'Skipped FK: inventario_sucursal.sucursal_id (table not found)';
    END IF;
END $$;

-- audit_log.sucursal_id -> sucursales.id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'audit_log'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE constraint_name = 'fk_audit_log_sucursal_id' 
            AND table_name = 'audit_log'
        ) THEN
            ALTER TABLE public.audit_log 
            ADD CONSTRAINT fk_audit_log_sucursal_id 
            FOREIGN KEY (sucursal_id) REFERENCES public.sucursales(id) ON DELETE CASCADE;
            RAISE NOTICE 'Added FK: audit_log.sucursal_id -> sucursales.id';
        END IF;
    ELSE
        RAISE NOTICE 'Skipped FK: audit_log.sucursal_id (table not found)';
    END IF;
END $$;

-- eventos.sucursal_id -> sucursales.id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'eventos'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE constraint_name = 'fk_eventos_sucursal_id' 
            AND table_name = 'eventos'
        ) THEN
            ALTER TABLE public.eventos 
            ADD CONSTRAINT fk_eventos_sucursal_id 
            FOREIGN KEY (sucursal_id) REFERENCES public.sucursales(id) ON DELETE CASCADE;
            RAISE NOTICE 'Added FK: eventos.sucursal_id -> sucursales.id';
        END IF;
    ELSE
        RAISE NOTICE 'Skipped FK: eventos.sucursal_id (table not found)';
    END IF;
END $$;

-- notificaciones.sucursal_id -> sucursales.id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'notificaciones'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE constraint_name = 'fk_notificaciones_sucursal_id' 
            AND table_name = 'notificaciones'
        ) THEN
            ALTER TABLE public.notificaciones 
            ADD CONSTRAINT fk_notificaciones_sucursal_id 
            FOREIGN KEY (sucursal_id) REFERENCES public.sucursales(id) ON DELETE CASCADE;
            RAISE NOTICE 'Added FK: notificaciones.sucursal_id -> sucursales.id';
        END IF;
    ELSE
        RAISE NOTICE 'Skipped FK: notificaciones.sucursal_id (table not found)';
    END IF;
END $$;

-- venta_detalle.sucursal_id -> sucursales.id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_venta_detalle_sucursal_id' 
        AND table_name = 'venta_detalle'
    ) THEN
        ALTER TABLE public.venta_detalle 
        ADD CONSTRAINT fk_venta_detalle_sucursal_id 
        FOREIGN KEY (sucursal_id) REFERENCES public.sucursales(id) ON DELETE RESTRICT;
        RAISE NOTICE 'Added FK: venta_detalle.sucursal_id -> sucursales.id';
    END IF;
END $$;

-- compras_detalle.sucursal_id -> sucursales.id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_compras_detalle_sucursal_id' 
        AND table_name = 'compras_detalle'
    ) THEN
        ALTER TABLE public.compras_detalle 
        ADD CONSTRAINT fk_compras_detalle_sucursal_id 
        FOREIGN KEY (sucursal_id) REFERENCES public.sucursales(id) ON DELETE RESTRICT;
        RAISE NOTICE 'Added FK: compras_detalle.sucursal_id -> sucursales.id';
    END IF;
END $$;

-- =====================================================
-- SECTION 3: Special Foreign Keys for transferencias_stock
-- =====================================================

-- transferencias_stock has both origen and destino sucursal_id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'transferencias_stock'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE constraint_name = 'fk_transferencias_stock_sucursal_origen_id' 
            AND table_name = 'transferencias_stock'
        ) THEN
            ALTER TABLE public.transferencias_stock 
            ADD CONSTRAINT fk_transferencias_stock_sucursal_origen_id 
            FOREIGN KEY (sucursal_origen_id) REFERENCES public.sucursales(id) ON DELETE RESTRICT;
            RAISE NOTICE 'Added FK: transferencias_stock.sucursal_origen_id -> sucursales.id';
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE constraint_name = 'fk_transferencias_stock_sucursal_destino_id' 
            AND table_name = 'transferencias_stock'
        ) THEN
            ALTER TABLE public.transferencias_stock 
            ADD CONSTRAINT fk_transferencias_stock_sucursal_destino_id 
            FOREIGN KEY (sucursal_destino_id) REFERENCES public.sucursales(id) ON DELETE RESTRICT;
            RAISE NOTICE 'Added FK: transferencias_stock.sucursal_destino_id -> sucursales.id';
        END IF;
    ELSE
        RAISE NOTICE 'Skipped FK: transferencias_stock (table not found)';
    END IF;
END $$;

-- =====================================================
-- SECTION 4: Foreign Keys for usuarios_sucursales junction table
-- =====================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_usuarios_sucursales_negocio_id' 
        AND table_name = 'usuarios_sucursales'
    ) THEN
        ALTER TABLE public.usuarios_sucursales 
        ADD CONSTRAINT fk_usuarios_sucursales_negocio_id 
        FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added FK: usuarios_sucursales.negocio_id -> negocios.id';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_usuarios_sucursales_sucursal_id' 
        AND table_name = 'usuarios_sucursales'
    ) THEN
        ALTER TABLE public.usuarios_sucursales 
        ADD CONSTRAINT fk_usuarios_sucursales_sucursal_id 
        FOREIGN KEY (sucursal_id) REFERENCES public.sucursales(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added FK: usuarios_sucursales.sucursal_id -> sucursales.id';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_usuarios_sucursales_usuario_id' 
        AND table_name = 'usuarios_sucursales'
    ) THEN
        ALTER TABLE public.usuarios_sucursales 
        ADD CONSTRAINT fk_usuarios_sucursales_usuario_id 
        FOREIGN KEY (usuario_id) REFERENCES public.usuarios(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added FK: usuarios_sucursales.usuario_id -> usuarios.id';
    END IF;
END $$;

-- =====================================================
-- Summary
-- =====================================================
DO $$
BEGIN
    RAISE NOTICE '==============================================';
    RAISE NOTICE 'Migration 04 completed successfully';
    RAISE NOTICE 'All foreign key constraints have been added';
    RAISE NOTICE '==============================================';
END $$;
