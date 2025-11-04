-- =======================================================================================
-- Migration 09: Enforce catalog uniqueness per business
-- Context     : Guarantees that productos/servicios remain unique at negocio level while
--               sucursal-specific overrides continue viviendo en producto_sucursal.
-- Safe to run : Yes. All statements are guarded and idempotent.
-- =======================================================================================

SET search_path TO public;

DO $$
BEGIN
    -- Productos: ensure combination (negocio_id, lower(trim(sku))) is unique when SKU present.
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'productos'
          AND column_name = 'sku'
    ) THEN
        EXECUTE '
            CREATE UNIQUE INDEX IF NOT EXISTS idx_productos_negocio_sku_unique
                ON public.productos (negocio_id, lower(btrim(sku)))
                WHERE sku IS NOT NULL AND btrim(sku) <> '''';
        ';
    ELSE
        RAISE NOTICE 'Skipping idx_productos_negocio_sku_unique (column productos.sku not found).';
    END IF;

    -- Productos: fallback uniqueness by nombre when SKU absent.
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'productos'
          AND column_name = 'nombre'
    ) THEN
        EXECUTE '
            CREATE UNIQUE INDEX IF NOT EXISTS idx_productos_negocio_nombre_unique
                ON public.productos (negocio_id, lower(btrim(nombre)))
                WHERE nombre IS NOT NULL AND btrim(nombre) <> '''';
        ';
    ELSE
        RAISE NOTICE 'Skipping idx_productos_negocio_nombre_unique (column productos.nombre not found).';
    END IF;

    -- Servicios: enforce uniqueness by nombre (servicios no manejan SKU).
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'servicios'
          AND column_name = 'nombre'
    ) THEN
        EXECUTE '
            CREATE UNIQUE INDEX IF NOT EXISTS idx_servicios_negocio_nombre_unique
                ON public.servicios (negocio_id, lower(btrim(nombre)))
                WHERE nombre IS NOT NULL AND btrim(nombre) <> '''';
        ';
    ELSE
        RAISE NOTICE 'Skipping idx_servicios_negocio_nombre_unique (column servicios.nombre not found).';
    END IF;
END;
$$;

DO $$
BEGIN
    RAISE NOTICE 'migration_09_enforce_catalog_uniqueness executed.';
END;
$$;
