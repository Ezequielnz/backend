-- =======================================================================================
-- Migration 08: Reporting Views and Metrics Helpers
-- Context      : Step 7 - Optimization and documentation for multi-negocio rollout
-- Description  : Creates reusable reporting views/functions for branch and business
--                level dashboards and ensures supporting analytics indexes exist.
-- Safe to run  : Yes (idempotent; guarded with existence checks)
-- =======================================================================================

-- ---------------------------------------------------------------------------------------
-- Helper: create index only when the target table/columns exist.
-- (Scoped copy to keep the script self-contained; see migration_05 for original helper.)
-- ---------------------------------------------------------------------------------------
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
    col_expr_item text;
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
        RAISE NOTICE 'Skipping index %: %.% does not exist', p_index_name, p_schema, p_table_name;
        RETURN;
    END IF;

    IF p_columns IS NULL OR array_length(p_columns, 1) = 0 THEN
        RAISE NOTICE 'Skipping index %: no columns provided', p_index_name;
        RETURN;
    END IF;

    FOR col_expr_item IN SELECT unnest(p_columns)
    LOOP
        col_name := trim(both '"' from split_part(col_expr_item, ' ', 1));
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
                WHEN position(' ' IN col_expr_value) > 0 THEN
                    format(
                        '%I %s',
                        split_part(col_expr_value, ' ', 1),
                        trim(substring(col_expr_value FROM position(' ' IN col_expr_value) + 1))
                    )
                ELSE
                    format('%I', col_expr_value)
            END
        FROM unnest(p_columns) AS col_expr_value
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

-- ---------------------------------------------------------------------------------------
-- Optional analytics indexes (daily reporting friendly)
-- ---------------------------------------------------------------------------------------
SELECT public.ensure_index_columns('idx_ventas_negocio_fecha', 'ventas', ARRAY['negocio_id', 'fecha']);
SELECT public.ensure_index_columns('idx_ventas_negocio_created_at', 'ventas', ARRAY['negocio_id', 'created_at']);
SELECT public.ensure_index_columns('idx_compras_negocio_fecha_compra', 'compras', ARRAY['negocio_id', 'fecha_compra']);
SELECT public.ensure_index_columns('idx_compras_negocio_created_at', 'compras', ARRAY['negocio_id', 'created_at']);

-- ---------------------------------------------------------------------------------------
-- Reporting view: business-level daily summary (ventas vs compras)
-- ---------------------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'ventas'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'compras'
    ) THEN
        EXECUTE $view$
        CREATE OR REPLACE VIEW public.vw_resumen_financiero_negocio AS
        WITH ventas AS (
            SELECT
                v.negocio_id,
                (date_trunc('day', COALESCE(v.fecha, v.created_at)))::date AS fecha,
                SUM(v.total) AS total_ventas,
                COUNT(*) AS cantidad_ventas
            FROM public.ventas v
            GROUP BY v.negocio_id, date_trunc('day', COALESCE(v.fecha, v.created_at))
        ),
        compras AS (
            SELECT
                c.negocio_id,
                (date_trunc('day', COALESCE(c.fecha_compra, c.fecha, c.created_at)))::date AS fecha,
                SUM(c.total) AS total_compras,
                COUNT(*) AS cantidad_compras
            FROM public.compras c
            GROUP BY c.negocio_id, date_trunc('day', COALESCE(c.fecha_compra, c.fecha, c.created_at))
        ),
        fechas AS (
            SELECT negocio_id, fecha FROM ventas
            UNION
            SELECT negocio_id, fecha FROM compras
        )
        SELECT
            f.negocio_id,
            n.nombre AS negocio_nombre,
            f.fecha,
            COALESCE(v.total_ventas, 0)::numeric(18,2) AS total_ventas,
            COALESCE(v.cantidad_ventas, 0)::bigint AS cantidad_ventas,
            COALESCE(c.total_compras, 0)::numeric(18,2) AS total_compras,
            COALESCE(c.cantidad_compras, 0)::bigint AS cantidad_compras,
            COALESCE(v.total_ventas, 0)::numeric(18,2) - COALESCE(c.total_compras, 0)::numeric(18,2) AS balance
        FROM fechas f
        LEFT JOIN ventas v ON v.negocio_id = f.negocio_id AND v.fecha = f.fecha
        LEFT JOIN compras c ON c.negocio_id = f.negocio_id AND c.fecha = f.fecha
        LEFT JOIN public.negocios n ON n.id = f.negocio_id;
        $view$;
        RAISE NOTICE 'Created/updated view public.vw_resumen_financiero_negocio';
    ELSE
        RAISE NOTICE 'Skipped view public.vw_resumen_financiero_negocio (ventas/compras tables not present)';
    END IF;
END$$;

-- ---------------------------------------------------------------------------------------
-- Reporting view: branch-level daily summary with business join
-- ---------------------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'ventas'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'ventas' AND column_name = 'sucursal_id'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'compras'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'compras' AND column_name = 'sucursal_id'
    ) THEN
        EXECUTE $view$
        CREATE OR REPLACE VIEW public.vw_resumen_financiero_sucursal AS
        WITH ventas AS (
            SELECT
                v.negocio_id,
                v.sucursal_id,
                (date_trunc('day', COALESCE(v.fecha, v.created_at)))::date AS fecha,
                SUM(v.total) AS total_ventas,
                COUNT(*) AS cantidad_ventas
            FROM public.ventas v
            GROUP BY v.negocio_id, v.sucursal_id, date_trunc('day', COALESCE(v.fecha, v.created_at))
        ),
        compras AS (
            SELECT
                c.negocio_id,
                c.sucursal_id,
                (date_trunc('day', COALESCE(c.fecha_compra, c.fecha, c.created_at)))::date AS fecha,
                SUM(c.total) AS total_compras,
                COUNT(*) AS cantidad_compras
            FROM public.compras c
            GROUP BY c.negocio_id, c.sucursal_id, date_trunc('day', COALESCE(c.fecha_compra, c.fecha, c.created_at))
        ),
        fechas AS (
            SELECT negocio_id, sucursal_id, fecha FROM ventas
            UNION
            SELECT negocio_id, sucursal_id, fecha FROM compras
        )
        SELECT
            f.negocio_id,
            n.nombre AS negocio_nombre,
            f.sucursal_id,
            s.nombre AS sucursal_nombre,
            s.is_main,
            f.fecha,
            COALESCE(v.total_ventas, 0)::numeric(18,2) AS total_ventas,
            COALESCE(v.cantidad_ventas, 0)::bigint AS cantidad_ventas,
            COALESCE(c.total_compras, 0)::numeric(18,2) AS total_compras,
            COALESCE(c.cantidad_compras, 0)::bigint AS cantidad_compras,
            COALESCE(v.total_ventas, 0)::numeric(18,2) - COALESCE(c.total_compras, 0)::numeric(18,2) AS balance
        FROM fechas f
        LEFT JOIN ventas v ON v.negocio_id = f.negocio_id AND v.sucursal_id IS NOT DISTINCT FROM f.sucursal_id AND v.fecha = f.fecha
        LEFT JOIN compras c ON c.negocio_id = f.negocio_id AND c.sucursal_id IS NOT DISTINCT FROM f.sucursal_id AND c.fecha = f.fecha
        LEFT JOIN public.negocios n ON n.id = f.negocio_id
        LEFT JOIN public.sucursales s ON s.id = f.sucursal_id;
        $view$;
        RAISE NOTICE 'Created/updated view public.vw_resumen_financiero_sucursal';
    ELSE
        RAISE NOTICE 'Skipped view public.vw_resumen_financiero_sucursal (ventas/compras.sucursal_id not present)';
    END IF;
END$$;

-- ---------------------------------------------------------------------------------------
-- Reporting view: top productos per negocio (for dashboard charts)
-- ---------------------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'venta_detalle'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'venta_detalle' AND column_name = 'subtotal'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'ventas'
    ) THEN
        EXECUTE $view$
        CREATE OR REPLACE VIEW public.vw_top_productos_por_negocio AS
        SELECT
            v.negocio_id,
            p.id AS producto_id,
            p.nombre AS producto_nombre,
            SUM(vd.cantidad)::bigint AS unidades_vendidas,
            SUM(vd.subtotal)::numeric(18,2) AS total_vendido,
            RANK() OVER (PARTITION BY v.negocio_id ORDER BY SUM(vd.subtotal) DESC) AS ranking
        FROM public.venta_detalle vd
        INNER JOIN public.ventas v ON v.id = vd.venta_id
        LEFT JOIN public.productos p ON p.id = vd.producto_id
        GROUP BY v.negocio_id, p.id, p.nombre;
        $view$;
        RAISE NOTICE 'Created/updated view public.vw_top_productos_por_negocio';
    ELSE
        RAISE NOTICE 'Skipped view public.vw_top_productos_por_negocio (ventas/venta_detalle tables not present)';
    END IF;
END$$;

-- ---------------------------------------------------------------------------------------
-- Function: consolidated financial summary (business or branch scope)
-- ---------------------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'ventas'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'compras'
    ) THEN
        EXECUTE $fn$
        CREATE OR REPLACE FUNCTION public.fn_resumen_financiero(
            p_negocio_id uuid,
            p_sucursal_id uuid DEFAULT NULL,
            p_desde date DEFAULT (CURRENT_DATE - INTERVAL '30 days'),
            p_hasta date DEFAULT CURRENT_DATE
        )
        RETURNS TABLE (
            fecha date,
            total_ventas numeric,
            cantidad_ventas bigint,
            total_compras numeric,
            cantidad_compras bigint,
            balance numeric
        )
        LANGUAGE sql
        STABLE
        AS $function$
        WITH ventas AS (
            SELECT
                v.negocio_id,
                v.sucursal_id,
                (date_trunc('day', COALESCE(v.fecha, v.created_at)))::date AS fecha,
                SUM(v.total)::numeric(18,2) AS total_ventas,
                COUNT(*)::bigint AS cantidad_ventas
            FROM public.ventas v
            GROUP BY v.negocio_id, v.sucursal_id, date_trunc('day', COALESCE(v.fecha, v.created_at))
        ),
        compras AS (
            SELECT
                c.negocio_id,
                c.sucursal_id,
                (date_trunc('day', COALESCE(c.fecha_compra, c.fecha, c.created_at)))::date AS fecha,
                SUM(c.total)::numeric(18,2) AS total_compras,
                COUNT(*)::bigint AS cantidad_compras
            FROM public.compras c
            GROUP BY c.negocio_id, c.sucursal_id, date_trunc('day', COALESCE(c.fecha_compra, c.fecha, c.created_at))
        ),
        fechas AS (
            SELECT negocio_id, sucursal_id, fecha FROM ventas
            UNION
            SELECT negocio_id, sucursal_id, fecha FROM compras
        )
        SELECT
            f.fecha,
            COALESCE(v.total_ventas, 0) AS total_ventas,
            COALESCE(v.cantidad_ventas, 0) AS cantidad_ventas,
            COALESCE(c.total_compras, 0) AS total_compras,
            COALESCE(c.cantidad_compras, 0) AS cantidad_compras,
            COALESCE(v.total_ventas, 0) - COALESCE(c.total_compras, 0) AS balance
        FROM fechas f
        LEFT JOIN ventas v ON v.negocio_id = f.negocio_id AND v.sucursal_id IS NOT DISTINCT FROM f.sucursal_id AND v.fecha = f.fecha
        LEFT JOIN compras c ON c.negocio_id = f.negocio_id AND c.sucursal_id IS NOT DISTINCT FROM f.sucursal_id AND c.fecha = f.fecha
        WHERE f.negocio_id = p_negocio_id
          AND (p_sucursal_id IS NULL OR f.sucursal_id = p_sucursal_id)
          AND f.fecha BETWEEN COALESCE(p_desde, DATE '1900-01-01') AND COALESCE(p_hasta, DATE '2999-12-31')
        ORDER BY f.fecha;
        $function$;
        $fn$;
        RAISE NOTICE 'Created/updated function public.fn_resumen_financiero(uuid, uuid, date, date)';
    ELSE
        RAISE NOTICE 'Skipped function public.fn_resumen_financiero (ventas/compras tables not present)';
    END IF;
END$$;

-- ---------------------------------------------------------------------------------------
-- Clean up helper to match previous migration convention
-- ---------------------------------------------------------------------------------------
DROP FUNCTION IF EXISTS public.ensure_index_columns(text, text, text[], text, text);
