-- =====================================================
-- Migration 03: Add Missing negocio_id and sucursal_id Columns
-- =====================================================
-- Description: Adds missing negocio_id and sucursal_id columns to operational tables
-- Author: Database Migration Script
-- Date: 2025-01-20
-- =====================================================

-- =====================================================
-- SECTION 1: Add negocio_id to tables that need it
-- =====================================================

-- Add negocio_id to usuarios (if missing)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'usuarios' 
                   AND column_name = 'negocio_id') THEN
        ALTER TABLE public.usuarios ADD COLUMN negocio_id UUID;
        RAISE NOTICE 'Added negocio_id to usuarios table';
    END IF;
END $$;

-- Add negocio_id to productos (if missing)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'productos' 
                   AND column_name = 'negocio_id') THEN
        ALTER TABLE public.productos ADD COLUMN negocio_id UUID;
        RAISE NOTICE 'Added negocio_id to productos table';
    END IF;
END $$;

-- Add negocio_id to clientes (if missing)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'clientes' 
                   AND column_name = 'negocio_id') THEN
        ALTER TABLE public.clientes ADD COLUMN negocio_id UUID;
        RAISE NOTICE 'Added negocio_id to clientes table';
    END IF;
END $$;

-- Add negocio_id to proveedores (if missing)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'proveedores' 
                   AND column_name = 'negocio_id') THEN
        ALTER TABLE public.proveedores ADD COLUMN negocio_id UUID;
        RAISE NOTICE 'Added negocio_id to proveedores table';
    END IF;
END $$;

-- Add negocio_id to ventas (if missing)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'ventas' 
                   AND column_name = 'negocio_id') THEN
        ALTER TABLE public.ventas ADD COLUMN negocio_id UUID;
        RAISE NOTICE 'Added negocio_id to ventas table';
    END IF;
END $$;

-- Add negocio_id to compras (if missing)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'compras' 
                   AND column_name = 'negocio_id') THEN
        ALTER TABLE public.compras ADD COLUMN negocio_id UUID;
        RAISE NOTICE 'Added negocio_id to compras table';
    END IF;
END $$;

-- Add negocio_id to inventario_sucursal (if missing)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' 
               AND table_name = 'inventario_sucursal') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_schema = 'public' 
                       AND table_name = 'inventario_sucursal' 
                       AND column_name = 'negocio_id') THEN
            ALTER TABLE public.inventario_sucursal ADD COLUMN negocio_id UUID;
            RAISE NOTICE 'Added negocio_id to inventario_sucursal table';
        END IF;
    ELSE
        RAISE NOTICE 'Skipped inventario_sucursal (table not found)';
    END IF;
END $$;

-- Add negocio_id to audit_log (if missing)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' 
               AND table_name = 'audit_log') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_schema = 'public' 
                       AND table_name = 'audit_log' 
                       AND column_name = 'negocio_id') THEN
            ALTER TABLE public.audit_log ADD COLUMN negocio_id UUID;
            RAISE NOTICE 'Added negocio_id to audit_log table';
        END IF;
    ELSE
        RAISE NOTICE 'Skipped audit_log (table not found)';
    END IF;
END $$;

-- Add negocio_id to eventos (if missing)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' 
               AND table_name = 'eventos') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_schema = 'public' 
                       AND table_name = 'eventos' 
                       AND column_name = 'negocio_id') THEN
            ALTER TABLE public.eventos ADD COLUMN negocio_id UUID;
            RAISE NOTICE 'Added negocio_id to eventos table';
        END IF;
    ELSE
        RAISE NOTICE 'Skipped eventos (table not found)';
    END IF;
END $$;

-- Add negocio_id to notificaciones (if missing)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' 
               AND table_name = 'notificaciones') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_schema = 'public' 
                       AND table_name = 'notificaciones' 
                       AND column_name = 'negocio_id') THEN
            ALTER TABLE public.notificaciones ADD COLUMN negocio_id UUID;
            RAISE NOTICE 'Added negocio_id to notificaciones table';
        END IF;
    ELSE
        RAISE NOTICE 'Skipped notificaciones (table not found)';
    END IF;
END $$;

-- Add negocio_id to transferencias_stock (if missing)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' 
               AND table_name = 'transferencias_stock') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_schema = 'public' 
                       AND table_name = 'transferencias_stock' 
                       AND column_name = 'negocio_id') THEN
            ALTER TABLE public.transferencias_stock ADD COLUMN negocio_id UUID;
            RAISE NOTICE 'Added negocio_id to transferencias_stock table';
        END IF;
    ELSE
        RAISE NOTICE 'Skipped transferencias_stock (table not found)';
    END IF;
END $$;

-- =====================================================
-- SECTION 2: Add sucursal_id to tables that need it
-- =====================================================

-- Add sucursal_id to ventas (if missing)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'ventas' 
                   AND column_name = 'sucursal_id') THEN
        ALTER TABLE public.ventas ADD COLUMN sucursal_id UUID;
        RAISE NOTICE 'Added sucursal_id to ventas table';
    END IF;
END $$;

-- Add sucursal_id to compras (if missing)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'compras' 
                   AND column_name = 'sucursal_id') THEN
        ALTER TABLE public.compras ADD COLUMN sucursal_id UUID;
        RAISE NOTICE 'Added sucursal_id to compras table';
    END IF;
END $$;

-- Add sucursal_id to inventario_sucursal (if missing)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' 
               AND table_name = 'inventario_sucursal') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_schema = 'public' 
                       AND table_name = 'inventario_sucursal' 
                       AND column_name = 'sucursal_id') THEN
            ALTER TABLE public.inventario_sucursal ADD COLUMN sucursal_id UUID;
            RAISE NOTICE 'Added sucursal_id to inventario_sucursal table';
        END IF;
    ELSE
        RAISE NOTICE 'Skipped inventario_sucursal.sucursal_id (table not found)';
    END IF;
END $$;

-- Add sucursal_id to audit_log (if missing)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' 
               AND table_name = 'audit_log') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_schema = 'public' 
                       AND table_name = 'audit_log' 
                       AND column_name = 'sucursal_id') THEN
            ALTER TABLE public.audit_log ADD COLUMN sucursal_id UUID;
            RAISE NOTICE 'Added sucursal_id to audit_log table';
        END IF;
    ELSE
        RAISE NOTICE 'Skipped audit_log.sucursal_id (table not found)';
    END IF;
END $$;

-- Add sucursal_id to eventos (if missing)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' 
               AND table_name = 'eventos') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_schema = 'public' 
                       AND table_name = 'eventos' 
                       AND column_name = 'sucursal_id') THEN
            ALTER TABLE public.eventos ADD COLUMN sucursal_id UUID;
            RAISE NOTICE 'Added sucursal_id to eventos table';
        END IF;
    ELSE
        RAISE NOTICE 'Skipped eventos.sucursal_id (table not found)';
    END IF;
END $$;

-- Add sucursal_id to notificaciones (if missing)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'public' 
               AND table_name = 'notificaciones') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_schema = 'public' 
                       AND table_name = 'notificaciones' 
                       AND column_name = 'sucursal_id') THEN
            ALTER TABLE public.notificaciones ADD COLUMN sucursal_id UUID;
            RAISE NOTICE 'Added sucursal_id to notificaciones table';
        END IF;
    ELSE
        RAISE NOTICE 'Skipped notificaciones.sucursal_id (table not found)';
    END IF;
END $$;

-- =====================================================
-- SECTION 3: Add negocio_id and sucursal_id to detail tables
-- =====================================================

-- Add negocio_id and sucursal_id to venta_detalle (if missing)
-- These will be populated from the parent venta record
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'venta_detalle' 
                   AND column_name = 'negocio_id') THEN
        ALTER TABLE public.venta_detalle ADD COLUMN negocio_id UUID;
        RAISE NOTICE 'Added negocio_id to venta_detalle table';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'venta_detalle' 
                   AND column_name = 'sucursal_id') THEN
        ALTER TABLE public.venta_detalle ADD COLUMN sucursal_id UUID;
        RAISE NOTICE 'Added sucursal_id to venta_detalle table';
    END IF;
END $$;

-- Add negocio_id and sucursal_id to compras_detalle (if missing)
-- These will be populated from the parent compra record
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'compras_detalle' 
                   AND column_name = 'negocio_id') THEN
        ALTER TABLE public.compras_detalle ADD COLUMN negocio_id UUID;
        RAISE NOTICE 'Added negocio_id to compras_detalle table';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'compras_detalle' 
                   AND column_name = 'sucursal_id') THEN
        ALTER TABLE public.compras_detalle ADD COLUMN sucursal_id UUID;
        RAISE NOTICE 'Added sucursal_id to compras_detalle table';
    END IF;
END $$;

-- =====================================================
-- SECTION 4: Optional - Add sucursal_id to usuarios
-- =====================================================
-- This is optional if you want to associate users with a specific branch

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'usuarios' 
                   AND column_name = 'sucursal_id') THEN
        ALTER TABLE public.usuarios ADD COLUMN sucursal_id UUID;
        RAISE NOTICE 'Added sucursal_id to usuarios table (optional - for default branch assignment)';
    END IF;
END $$;

-- =====================================================
-- SECTION 5: Data population for detail tables
-- =====================================================

-- Populate negocio_id and sucursal_id in venta_detalle from ventas
UPDATE public.venta_detalle vd
SET 
    negocio_id = v.negocio_id,
    sucursal_id = v.sucursal_id
FROM public.ventas v
WHERE vd.venta_id = v.id
AND (vd.negocio_id IS NULL OR vd.sucursal_id IS NULL);

-- Populate negocio_id and sucursal_id in compras_detalle from compras
UPDATE public.compras_detalle cd
SET 
    negocio_id = c.negocio_id,
    sucursal_id = c.sucursal_id
FROM public.compras c
WHERE cd.compra_id = c.id
AND (cd.negocio_id IS NULL OR cd.sucursal_id IS NULL);

-- =====================================================
-- SECTION 6: Create triggers to auto-populate detail tables
-- =====================================================

-- Trigger to auto-populate negocio_id and sucursal_id in venta_detalle
CREATE OR REPLACE FUNCTION populate_venta_detalle_ids()
RETURNS TRIGGER AS $$
BEGIN
    SELECT negocio_id, sucursal_id INTO NEW.negocio_id, NEW.sucursal_id
    FROM public.ventas
    WHERE id = NEW.venta_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_populate_venta_detalle_ids ON public.venta_detalle;
CREATE TRIGGER trigger_populate_venta_detalle_ids
    BEFORE INSERT OR UPDATE ON public.venta_detalle
    FOR EACH ROW
    EXECUTE FUNCTION populate_venta_detalle_ids();

-- Trigger to auto-populate negocio_id and sucursal_id in compras_detalle
CREATE OR REPLACE FUNCTION populate_compras_detalle_ids()
RETURNS TRIGGER AS $$
BEGIN
    SELECT negocio_id, sucursal_id INTO NEW.negocio_id, NEW.sucursal_id
    FROM public.compras
    WHERE id = NEW.compra_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_populate_compras_detalle_ids ON public.compras_detalle;
CREATE TRIGGER trigger_populate_compras_detalle_ids
    BEFORE INSERT OR UPDATE ON public.compras_detalle
    FOR EACH ROW
    EXECUTE FUNCTION populate_compras_detalle_ids();

-- =====================================================
-- Summary
-- =====================================================
DO $$
BEGIN
    RAISE NOTICE '==============================================';
    RAISE NOTICE 'Migration 03 completed successfully';
    RAISE NOTICE 'Added negocio_id and sucursal_id columns where needed';
    RAISE NOTICE 'Created triggers for auto-population in detail tables';
    RAISE NOTICE '==============================================';
END $$;
