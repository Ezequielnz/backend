-- =====================================================
-- Migration 05: Create Performance Indexes (guarded)
-- =====================================================
-- Description: Ensures that branch-aware indexes exist only when the underlying
--              tables and columns are available in the current Supabase schema.
-- Author: Database Migration Script
-- Date: 2025-01-20
-- Last updated: 2025-02-XX (guarded for missing tables/columns)
-- =====================================================

-- Helper function: create an index only if the table and required columns exist
DROP FUNCTION IF EXISTS public.ensure_index_columns(text, text, text[], text, text);

CREATE OR REPLACE FUNCTION public.ensure_index_columns(
    p_index_name text,
    p_table_name text,
    p_columns text[],
    p_where text DEFAULT NULL,
    p_schema text DEFAULT 'public'
) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    missing_columns text[] := ARRAY[]::text[];
    col_expr text;
    col_name text;
    column_list text;
    formatted_columns text[];
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = p_schema
          AND table_name = p_table_name
    ) THEN
        RAISE NOTICE 'Skipping index %: table %.% does not exist', p_index_name, p_schema, p_table_name;
        RETURN;
    END IF;

    IF p_columns IS NULL OR array_length(p_columns, 1) = 0 THEN
        RAISE NOTICE 'Skipping index %: no columns provided', p_index_name;
        RETURN;
    END IF;

    FOR col_expr IN SELECT unnest(p_columns)
    LOOP
        col_name := trim(both '"' from split_part(col_expr, ' ', 1));
        col_name := regexp_replace(col_name, '[\(\)]', '', 'g');

        IF col_name <> '' AND NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = p_schema
              AND table_name = p_table_name
              AND column_name = col_name
        ) THEN
            missing_columns := array_append(missing_columns, col_name);
        END IF;
    END LOOP;

    IF array_length(missing_columns, 1) IS NOT NULL THEN
        RAISE NOTICE 'Skipping index %: missing columns % on %.%', p_index_name, missing_columns, p_schema, p_table_name;
        RETURN;
    END IF;

    formatted_columns := ARRAY(
        SELECT
            CASE
                WHEN position(' ' IN col_expr) > 0 THEN
                    format(
                        '%I %s',
                        split_part(col_expr, ' ', 1),
                        trim(substring(col_expr FROM position(' ' IN col_expr) + 1))
                    )
                ELSE
                    format('%I', col_expr)
            END
        FROM unnest(p_columns) AS col_expr
    );

    column_list := array_to_string(formatted_columns, ', ');

    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS %I ON %I.%I (%s)%s',
        p_index_name,
        p_schema,
        p_table_name,
        column_list,
        CASE WHEN p_where IS NOT NULL THEN ' WHERE ' || p_where ELSE '' END
    );

    RAISE NOTICE 'Ensured index % on %.%', p_index_name, p_schema, p_table_name;
END;
$$;

-- =====================================================
-- SECTION 1: negocio_id indexes for core tenant tables
-- =====================================================
SELECT public.ensure_index_columns('idx_usuarios_negocio_id', 'usuarios', ARRAY['negocio_id']);
SELECT public.ensure_index_columns('idx_productos_negocio_id', 'productos', ARRAY['negocio_id']);
SELECT public.ensure_index_columns('idx_clientes_negocio_id', 'clientes', ARRAY['negocio_id']);
SELECT public.ensure_index_columns('idx_proveedores_negocio_id', 'proveedores', ARRAY['negocio_id']);
SELECT public.ensure_index_columns('idx_ventas_negocio_id', 'ventas', ARRAY['negocio_id']);
SELECT public.ensure_index_columns('idx_compras_negocio_id', 'compras', ARRAY['negocio_id']);
SELECT public.ensure_index_columns('idx_usuarios_sucursales_negocio_id', 'usuarios_sucursales', ARRAY['negocio_id']);
SELECT public.ensure_index_columns('idx_venta_detalle_negocio_id', 'venta_detalle', ARRAY['negocio_id']);
SELECT public.ensure_index_columns('idx_compras_detalle_negocio_id', 'compras_detalle', ARRAY['negocio_id']);

-- =====================================================
-- SECTION 2: sucursal_id indexes for branch-aware tables
-- =====================================================
SELECT public.ensure_index_columns('idx_usuarios_sucursal_id', 'usuarios', ARRAY['sucursal_id']);
SELECT public.ensure_index_columns('idx_ventas_sucursal_id', 'ventas', ARRAY['sucursal_id']);
SELECT public.ensure_index_columns('idx_compras_sucursal_id', 'compras', ARRAY['sucursal_id']);
SELECT public.ensure_index_columns('idx_usuarios_sucursales_sucursal_id', 'usuarios_sucursales', ARRAY['sucursal_id']);
SELECT public.ensure_index_columns('idx_venta_detalle_sucursal_id', 'venta_detalle', ARRAY['sucursal_id']);
SELECT public.ensure_index_columns('idx_compras_detalle_sucursal_id', 'compras_detalle', ARRAY['sucursal_id']);

-- =====================================================
-- SECTION 3: composite indexes for frequent lookups
-- =====================================================
SELECT public.ensure_index_columns('idx_ventas_negocio_sucursal', 'ventas', ARRAY['negocio_id', 'sucursal_id']);
SELECT public.ensure_index_columns('idx_ventas_negocio_sucursal_fecha', 'ventas', ARRAY['negocio_id', 'sucursal_id', 'fecha']);

SELECT public.ensure_index_columns('idx_compras_negocio_sucursal', 'compras', ARRAY['negocio_id', 'sucursal_id']);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'compras'
          AND column_name = 'fecha_compra'
    ) THEN
        PERFORM public.ensure_index_columns(
            'idx_compras_negocio_sucursal_fecha_compra',
            'compras',
            ARRAY['negocio_id', 'sucursal_id', 'fecha_compra']
        );
    ELSIF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'compras'
          AND column_name = 'fecha'
    ) THEN
        PERFORM public.ensure_index_columns(
            'idx_compras_negocio_sucursal_fecha',
            'compras',
            ARRAY['negocio_id', 'sucursal_id', 'fecha']
        );
    ELSIF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'compras'
          AND column_name = 'creado_en'
    ) THEN
        PERFORM public.ensure_index_columns(
            'idx_compras_negocio_sucursal_creado_en',
            'compras',
            ARRAY['negocio_id', 'sucursal_id', 'creado_en']
        );
    ELSIF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'compras'
          AND column_name = 'created_at'
    ) THEN
        PERFORM public.ensure_index_columns(
            'idx_compras_negocio_sucursal_created_at',
            'compras',
            ARRAY['negocio_id', 'sucursal_id', 'created_at']
        );
    ELSE
        RAISE NOTICE 'compras: no timestamp column found; using (negocio_id, sucursal_id) index only';
    END IF;
END $$;

SELECT public.ensure_index_columns('idx_venta_detalle_venta_producto', 'venta_detalle', ARRAY['venta_id', 'producto_id']);
SELECT public.ensure_index_columns('idx_compras_detalle_compra_producto', 'compras_detalle', ARRAY['compra_id', 'producto_id']);
SELECT public.ensure_index_columns('idx_usuarios_sucursales_usuario_sucursal', 'usuarios_sucursales', ARRAY['usuario_id', 'sucursal_id']);
SELECT public.ensure_index_columns('idx_usuarios_sucursales_usuario_id', 'usuarios_sucursales', ARRAY['usuario_id']);

-- =====================================================
-- SECTION 4: optional state-based indexes (only if column exists)
-- =====================================================
SELECT public.ensure_index_columns(
    'idx_productos_negocio_estado',
    'productos',
    ARRAY['negocio_id', 'estado'],
    'estado = ''activo'''
);

SELECT public.ensure_index_columns(
    'idx_clientes_negocio_estado',
    'clientes',
    ARRAY['negocio_id', 'estado']
);

SELECT public.ensure_index_columns(
    'idx_proveedores_negocio_estado',
    'proveedores',
    ARRAY['negocio_id', 'estado']
);

SELECT public.ensure_index_columns(
    'idx_ventas_negocio_estado',
    'ventas',
    ARRAY['negocio_id', 'estado']
);

SELECT public.ensure_index_columns(
    'idx_compras_negocio_estado',
    'compras',
    ARRAY['negocio_id', 'estado']
);

-- =====================================================
-- SECTION 5: analyze existing tables to refresh statistics
-- =====================================================
DO $$
DECLARE
    table_name text;
BEGIN
    FOR table_name IN
        SELECT unnest(ARRAY[
            'negocios',
            'sucursales',
            'usuarios',
            'usuarios_sucursales',
            'productos',
            'clientes',
            'proveedores',
            'ventas',
            'venta_detalle',
            'compras',
            'compras_detalle'
        ])
    LOOP
        IF EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = table_name
        ) THEN
            EXECUTE format('ANALYZE %I.%I', 'public', table_name);
            RAISE NOTICE 'Analyzed %.%', 'public', table_name;
        ELSE
            RAISE NOTICE 'Skipping ANALYZE for %.% (table not found)', 'public', table_name;
        END IF;
    END LOOP;
END $$;

-- Clean up helper to avoid leaving utility functions behind
DROP FUNCTION IF EXISTS public.ensure_index_columns(text, text, text[], text, text);

-- =====================================================
-- Summary (dynamic)
-- =====================================================
DO $$
BEGIN
    RAISE NOTICE '==============================================';
    RAISE NOTICE 'Migration 05 executed with guarded index creation';
    RAISE NOTICE 'Indexes and ANALYZE operations ran only for existing tables/columns';
    RAISE NOTICE 'Check preceding NOTICE logs to confirm which objects were created';
    RAISE NOTICE '==============================================';
END $$;
