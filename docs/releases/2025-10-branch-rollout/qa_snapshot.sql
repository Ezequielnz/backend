DO $$
DECLARE
    tables text[] := ARRAY[
        'usuarios',
        'sucursales',
        'ventas',
        'compras',
        'venta_detalle',
        'compras_detalle',
        'productos',
        'clientes',
        'proveedores',
        'usuarios_sucursales'
    ];
    table_entry text;
    has_negocio boolean;
    has_sucursal boolean;
    null_negocio bigint;
    null_sucursal bigint;
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_tables
        WHERE schemaname = 'pg_temp'
          AND tablename = 'qa_branch_results'
    ) THEN
        EXECUTE 'DROP TABLE qa_branch_results';
    END IF;

    EXECUTE '
        CREATE TEMP TABLE qa_branch_results (
            table_name text PRIMARY KEY,
            has_negocio_id boolean,
            has_sucursal_id boolean,
            null_negocio_id bigint,
            null_sucursal_id bigint
        ) ON COMMIT DROP
    ';

    FOREACH table_entry IN ARRAY tables
    LOOP
        has_negocio := EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = table_entry
              AND column_name = 'negocio_id'
        );

        has_sucursal := EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = table_entry
              AND column_name = 'sucursal_id'
        );

        IF EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = table_entry
        ) THEN
            IF has_negocio THEN
                EXECUTE format(
                    'SELECT COUNT(*) FROM %I.%I WHERE negocio_id IS NULL',
                    'public',
                    table_entry
                ) INTO null_negocio;
            ELSE
                null_negocio := NULL;
            END IF;

            IF has_sucursal THEN
                EXECUTE format(
                    'SELECT COUNT(*) FROM %I.%I WHERE sucursal_id IS NULL',
                    'public',
                    table_entry
                ) INTO null_sucursal;
            ELSE
                null_sucursal := NULL;
            END IF;
        ELSE
            null_negocio := NULL;
            null_sucursal := NULL;
            RAISE NOTICE 'Table %.% not found during QA checks', 'public', table_entry;
        END IF;

        INSERT INTO qa_branch_results (
            table_name,
            has_negocio_id,
            has_sucursal_id,
            null_negocio_id,
            null_sucursal_id
        )
        VALUES (
            table_entry,
            has_negocio,
            has_sucursal,
            null_negocio,
            null_sucursal
        );
    END LOOP;
END $$;

SELECT
    table_name,
    has_negocio_id,
    has_sucursal_id,
    null_negocio_id,
    null_sucursal_id
FROM qa_branch_results
ORDER BY table_name;

-- Detailed diagnostics for tables that still have NULLs ----------------------
-- Uncomment the sections below as needed during QA.

-- -- Usuarios without negocio reference
-- SELECT id, email, negocio_id, sucursal_id
-- FROM public.usuarios
-- WHERE negocio_id IS NULL OR sucursal_id IS NULL
-- ORDER BY created_at DESC
-- LIMIT 50;

-- -- Ventas without assigned branch
-- SELECT id, negocio_id, sucursal_id, fecha
-- FROM public.ventas
-- WHERE sucursal_id IS NULL OR negocio_id IS NULL
-- ORDER BY fecha DESC
-- LIMIT 50;

-- -- Compras without assigned branch
-- SELECT id, negocio_id, sucursal_id, COALESCE(fecha_compra, creado_en, created_at) AS referencia_fecha
-- FROM public.compras
-- WHERE sucursal_id IS NULL OR negocio_id IS NULL
-- ORDER BY referencia_fecha DESC
-- LIMIT 50;

-- -- Detalle tables without propagated IDs
-- SELECT id, venta_id, negocio_id, sucursal_id
-- FROM public.venta_detalle
-- WHERE negocio_id IS NULL OR sucursal_id IS NULL
-- ORDER BY created_at DESC
-- LIMIT 50;

-- SELECT id, compra_id, negocio_id, sucursal_id
-- FROM public.compras_detalle
-- WHERE negocio_id IS NULL OR sucursal_id IS NULL
-- ORDER BY created_at DESC
-- LIMIT 50;

-- Recommended remediation snippets ------------------------------------------
-- Run only after reviewing the diagnostics and ensuring the logic applies.

-- -- Backfill sucursal_id on ventas from existing branch assignments
-- UPDATE public.ventas v
-- SET sucursal_id = s.id
-- FROM public.sucursales s
-- WHERE v.sucursal_id IS NULL
--   AND s.negocio_id = v.negocio_id
--   AND s.codigo = 'principal';

-- -- Propagate branch information to venta_detalle
-- UPDATE public.venta_detalle vd
-- SET negocio_id = v.negocio_id,
--     sucursal_id = v.sucursal_id
-- FROM public.ventas v
-- WHERE vd.venta_id = v.id
--   AND (vd.negocio_id IS NULL OR vd.sucursal_id IS NULL);

-- -- Propagate branch information to compras_detalle
-- UPDATE public.compras_detalle cd
-- SET negocio_id = c.negocio_id,
--     sucursal_id = c.sucursal_id
-- FROM public.compras c
-- WHERE cd.compra_id = c.id
--   AND (cd.negocio_id IS NULL OR cd.sucursal_id IS NULL);
