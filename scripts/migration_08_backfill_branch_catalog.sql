-- =======================================================================================
-- Migration 08b: Backfill multi-sucursal catalog + inventory configuration
-- Context      : Complements structural migration that introduces negocio_configuracion,
--                producto_sucursal, servicio_sucursal e inventario_negocio.
-- Description  : (a) crea configuraciones por negocio, (b) replica catalogos existentes
--                hacia las tablas por sucursal, (c) consolida inventario por negocio
--                y (d) asegura que owners/admins tengan acceso a todas las sucursales.
-- Safe to run  : Si. Idempotente; todas las inserciones usan ON CONFLICT / DO NOTHING.
-- =======================================================================================

-- ---------------------------------------------------------------------------------------
-- Seccion 0: Validacion de dependencias (tablas y columnas esperadas)
-- ---------------------------------------------------------------------------------------
DO $$
DECLARE
    required_tables constant text[] := ARRAY[
        'public.negocios',
        'public.sucursales',
        'public.negocio_configuracion',
        'public.productos',
        'public.servicios',
        'public.producto_sucursal',
        'public.servicio_sucursal',
        'public.inventario_sucursal',
        'public.inventario_negocio',
        'public.usuarios_negocios',
        'public.usuarios_sucursales'
    ];
    missing_tables text[] := ARRAY[]::text[];
    tbl text;
BEGIN
    FOREACH tbl IN ARRAY required_tables LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE (table_schema || '.' || table_name) = tbl
        ) THEN
            missing_tables := array_append(missing_tables, tbl);
        END IF;
    END LOOP;

    IF array_length(missing_tables, 1) IS NOT NULL THEN
        RAISE EXCEPTION 'migration_08_backfill_branch_catalog: faltan tablas requeridas: %', array_to_string(missing_tables, ', ');
    END IF;

    -- Validar columnas criticas para evitar fallos silenciosos.
    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'negocio_configuracion'
      AND column_name = 'inventario_modo';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Tabla negocio_configuracion no posee columna inventario_modo; ejecutar migracion estructural previa.';
    END IF;

    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'producto_sucursal'
      AND column_name = 'sku_local';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Tabla producto_sucursal requiere columna sku_local.';
    END IF;

    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'servicio_sucursal'
      AND column_name = 'servicio_id';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Tabla servicio_sucursal requiere columna servicio_id.';
    END IF;

    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'inventario_sucursal'
      AND column_name = 'stock_actual';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Tabla inventario_sucursal requiere columna stock_actual.';
    END IF;

    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'inventario_negocio'
      AND column_name = 'stock_total';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Tabla inventario_negocio requiere columna stock_total.';
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------------------
-- Seccion 1: Crear configuraciones por negocio con valores por defecto
-- ---------------------------------------------------------------------------------------
WITH default_branch AS (
    SELECT
        s.negocio_id,
        s.id,
        ROW_NUMBER() OVER (
            PARTITION BY s.negocio_id
            ORDER BY
                CASE WHEN COALESCE(s.is_main, FALSE) THEN 0 ELSE 1 END,
                s.created_at,
                s.id
        ) AS rn
    FROM public.sucursales s
    WHERE COALESCE(s.estado, 'activa') <> 'cerrada'
)
INSERT INTO public.negocio_configuracion (
    negocio_id,
    inventario_modo,
    servicios_modo,
    catalogo_producto_modo,
    permite_transferencias,
    transferencia_auto_confirma,
    default_branch_id,
    metadata,
    created_at,
    updated_at
)
SELECT
    n.id,
    'por_sucursal',
    'por_sucursal',
    'por_sucursal',
    TRUE,
    FALSE,
    db.id,
    '{}'::jsonb,
    NOW(),
    NOW()
FROM public.negocios n
LEFT JOIN public.negocio_configuracion cfg ON cfg.negocio_id = n.id
LEFT JOIN default_branch db ON db.negocio_id = n.id AND db.rn = 1
WHERE cfg.negocio_id IS NULL
ON CONFLICT (negocio_id) DO NOTHING;

RAISE NOTICE 'negocio_configuracion: % registros creados', (SELECT COUNT(*) FROM public.negocio_configuracion);

-- ---------------------------------------------------------------------------------------
-- Seccion 2: Normalizacion de SKUs duplicados por negocio
-- ---------------------------------------------------------------------------------------
DO $$
DECLARE
    has_updated_at boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'productos'
          AND column_name = 'updated_at'
    ) INTO has_updated_at;

    WITH dup AS (
        SELECT
            id,
            negocio_id,
            sku,
            ROW_NUMBER() OVER (
                PARTITION BY negocio_id, NULLIF(btrim(sku), '')
                ORDER BY created_at, id
            ) AS rn
        FROM public.productos
        WHERE NULLIF(btrim(sku), '') IS NOT NULL
    )
    UPDATE public.productos p
    SET
        sku = CONCAT(p.sku, '-', RIGHT(p.id::text, 6)),
        updated_at = CASE WHEN has_updated_at THEN NOW() ELSE p.updated_at END
    FROM dup
    WHERE dup.id = p.id
      AND dup.rn > 1;

    RAISE NOTICE 'Normalizacion SKUs duplicados completada.';
END;
$$;

-- ---------------------------------------------------------------------------------------
-- Seccion 3: Backfill de producto_sucursal
-- ---------------------------------------------------------------------------------------
INSERT INTO public.producto_sucursal (
    id,
    negocio_id,
    sucursal_id,
    producto_id,
    precio,
    precio_costo,
    sku_local,
    stock_minimo,
    estado,
    visibilidad,
    metadata,
    created_at,
    updated_at
)
SELECT
    gen_random_uuid(),
    p.negocio_id,
    s.id,
    p.id,
    p.precio,
    p.precio_costo,
    COALESCE(NULLIF(p.sku, ''), CONCAT('SKU-', RIGHT(p.id::text, 6))),
    COALESCE(p.stock_minimo, 0),
    COALESCE(p.estado, 'activo'),
    COALESCE(p.visibilidad, 'publico'),
    COALESCE(p.metadata, '{}'::jsonb) || jsonb_build_object('source', 'migration_08_backfill_branch_catalog'),
    NOW(),
    NOW()
FROM public.productos p
JOIN public.sucursales s ON s.negocio_id = p.negocio_id
LEFT JOIN public.producto_sucursal ps
       ON ps.producto_id = p.id
      AND ps.sucursal_id = s.id
WHERE ps.id IS NULL;

RAISE NOTICE 'producto_sucursal: backfill completado (%).',
    (SELECT COUNT(*) FROM public.producto_sucursal);

-- ---------------------------------------------------------------------------------------
-- Seccion 4: Backfill de servicio_sucursal
-- ---------------------------------------------------------------------------------------
INSERT INTO public.servicio_sucursal (
    id,
    negocio_id,
    sucursal_id,
    servicio_id,
    precio,
    estado,
    visibilidad,
    metadata,
    created_at,
    updated_at
)
SELECT
    gen_random_uuid(),
    sv.negocio_id,
    s.id,
    sv.id,
    sv.precio,
    COALESCE(sv.estado, 'activo'),
    COALESCE(sv.visibilidad, 'publico'),
    COALESCE(sv.metadata, '{}'::jsonb) || jsonb_build_object('source', 'migration_08_backfill_branch_catalog'),
    NOW(),
    NOW()
FROM public.servicios sv
JOIN public.sucursales s ON s.negocio_id = sv.negocio_id
LEFT JOIN public.servicio_sucursal ss
       ON ss.servicio_id = sv.id
      AND ss.sucursal_id = s.id
WHERE ss.id IS NULL;

RAISE NOTICE 'servicio_sucursal: backfill completado (%).',
    (SELECT COUNT(*) FROM public.servicio_sucursal);

-- ---------------------------------------------------------------------------------------
-- Seccion 5: Inventario centralizado y sincronizacion
-- ---------------------------------------------------------------------------------------
INSERT INTO public.inventario_negocio (
    negocio_id,
    producto_id,
    stock_total,
    created_at,
    updated_at
)
SELECT
    isur.negocio_id,
    isur.producto_id,
    COALESCE(SUM(isur.stock_actual), 0),
    NOW(),
    NOW()
FROM public.inventario_sucursal isur
GROUP BY isur.negocio_id, isur.producto_id
ON CONFLICT (negocio_id, producto_id)
DO UPDATE
SET
    stock_total = EXCLUDED.stock_total,
    updated_at = NOW();

RAISE NOTICE 'inventario_negocio sincronizado (% registros).',
    (SELECT COUNT(*) FROM public.inventario_negocio);

-- ---------------------------------------------------------------------------------------
-- Seccion 6: Propagar asignaciones de usuarios a todas las sucursales del negocio
-- ---------------------------------------------------------------------------------------
INSERT INTO public.usuarios_sucursales (
    usuario_id,
    sucursal_id,
    rol,
    created_at,
    updated_at
)
SELECT
    un.usuario_id,
    s.id,
    CASE
        WHEN un.rol IN ('owner', 'admin') THEN 'admin'
        ELSE COALESCE(un.rol, 'staff')
    END,
    NOW(),
    NOW()
FROM public.usuarios_negocios un
JOIN public.sucursales s ON s.negocio_id = un.negocio_id
LEFT JOIN public.usuarios_sucursales us
       ON us.usuario_id = un.usuario_id
      AND us.sucursal_id = s.id
WHERE us.usuario_id IS NULL
  AND COALESCE(un.estado, 'activo') = 'activo';

RAISE NOTICE 'usuarios_sucursales: asignaciones reflejadas.';

-- ---------------------------------------------------------------------------------------
-- Seccion 7: Limpieza final y estadisticas
-- ---------------------------------------------------------------------------------------
ANALYZE public.negocio_configuracion;
ANALYZE public.producto_sucursal;
ANALYZE public.servicio_sucursal;
ANALYZE public.inventario_negocio;
ANALYZE public.usuarios_sucursales;

DO $$
BEGIN
    RAISE NOTICE 'migration_08_backfill_branch_catalog finalizada correctamente.';
END;
$$;
