-- Migration: Add sucursales, usuarios_sucursales, and sucursal_id FKs to ventas/venta_detalle/compras
-- Context: implements step "Add sucursales and usuarios_sucursales tables; add sucursal_id to ventas/venta_detalle/compras"
-- Preconditions: public.negocios, public.ventas, public.venta_detalle exist
-- Idempotency: Safe to re-run; uses IF NOT EXISTS and guards
-- Note: Branch-aware RLS will be applied by scripts/add_branch_aware_rls_policies.sql after this migration

-- 1) Create sucursales (branches)
CREATE TABLE IF NOT EXISTS public.sucursales (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    negocio_id UUID NOT NULL REFERENCES public.negocios(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL,
    codigo TEXT NOT NULL,
    direccion TEXT,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (negocio_id, codigo)
);

CREATE INDEX IF NOT EXISTS idx_sucursales_negocio_id ON public.sucursales(negocio_id);

-- 2) Create usuarios_sucursales (user-branch assignments)
CREATE TABLE IF NOT EXISTS public.usuarios_sucursales (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id UUID NOT NULL,
    negocio_id UUID NOT NULL REFERENCES public.negocios(id) ON DELETE CASCADE,
    sucursal_id UUID NOT NULL REFERENCES public.sucursales(id) ON DELETE CASCADE,
    rol_sucursal TEXT,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (usuario_id, sucursal_id)
);

CREATE INDEX IF NOT EXISTS idx_usuarios_sucursales_usuario_negocio ON public.usuarios_sucursales(usuario_id, negocio_id);
CREATE INDEX IF NOT EXISTS idx_usuarios_sucursales_sucursal_id ON public.usuarios_sucursales(sucursal_id);

-- 3) Add sucursal_id columns to ventas, venta_detalle and compras (if compras exists)
ALTER TABLE public.ventas
    ADD COLUMN IF NOT EXISTS sucursal_id UUID REFERENCES public.sucursales(id);

ALTER TABLE public.venta_detalle
    ADD COLUMN IF NOT EXISTS sucursal_id UUID REFERENCES public.sucursales(id);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'compras'
    ) THEN
        EXECUTE 'ALTER TABLE public.compras ADD COLUMN IF NOT EXISTS sucursal_id UUID REFERENCES public.sucursales(id)';
    END IF;
END $$;

-- 4) Recommended indexes for branch-aware queries
-- ventas: composite index by (negocio_id, sucursal_id, fecha)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public' AND indexname = 'idx_ventas_negocio_sucursal_fecha'
    ) THEN
        EXECUTE 'CREATE INDEX idx_ventas_negocio_sucursal_fecha ON public.ventas(negocio_id, sucursal_id, fecha)';
    END IF;
END $$;

-- venta_detalle: direct lookup by sucursal when needed
CREATE INDEX IF NOT EXISTS idx_venta_detalle_sucursal_id ON public.venta_detalle(sucursal_id);

-- compras: composite index by (negocio_id, sucursal_id, fecha) if compras exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'compras'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname = 'public' AND indexname = 'idx_compras_negocio_sucursal_fecha'
        ) THEN
            EXECUTE 'CREATE INDEX idx_compras_negocio_sucursal_fecha ON public.compras(negocio_id, sucursal_id, fecha)';
        END IF;
    END IF;
END $$;

-- 5) Backfill: create default "Principal" branch per negocio and set sucursal_id defaults
-- Create a default branch per business if missing
INSERT INTO public.sucursales (negocio_id, nombre, codigo, direccion)
SELECT n.id, 'Principal', 'principal', NULL
FROM public.negocios n
WHERE NOT EXISTS (
    SELECT 1 FROM public.sucursales s
    WHERE s.negocio_id = n.id AND s.codigo = 'principal'
);

-- ventas: set sucursal_id to the default branch if NULL
UPDATE public.ventas v
SET sucursal_id = s.id
FROM public.sucursales s
WHERE v.sucursal_id IS NULL
  AND s.negocio_id = v.negocio_id
  AND s.codigo = 'principal';

-- venta_detalle: inherit sucursal_id from parent venta
UPDATE public.venta_detalle vd
SET sucursal_id = v.sucursal_id
FROM public.ventas v
WHERE vd.sucursal_id IS NULL
  AND vd.venta_id = v.id
  AND v.sucursal_id IS NOT NULL;

-- compras: set sucursal_id to default branch when compras exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'compras'
    ) THEN
        EXECUTE $SQL$
        UPDATE public.compras c
        SET sucursal_id = s.id
        FROM public.sucursales s
        WHERE c.sucursal_id IS NULL
          AND s.negocio_id = c.negocio_id
          AND s.codigo = 'principal'
        $SQL$;
    END IF;
END $$;

-- 6) Comments for documentation
COMMENT ON TABLE public.sucursales IS 'Sucursales (branches) por negocio. Unique por (negocio_id, codigo).';
COMMENT ON COLUMN public.sucursales.codigo IS 'Código único por negocio. Se usa "principal" para la sucursal por defecto.';
COMMENT ON TABLE public.usuarios_sucursales IS 'Asignaciones de usuarios a sucursales dentro de un negocio.';

COMMENT ON COLUMN public.ventas.sucursal_id IS 'Sucursal asociada a la venta (FK sucursales.id).';
COMMENT ON COLUMN public.venta_detalle.sucursal_id IS 'Sucursal asociada al detalle de venta (heredada de la venta).';
-- compras.sucursal_id comment will be present if the column exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'compras' AND column_name = 'sucursal_id'
    ) THEN
        EXECUTE 'COMMENT ON COLUMN public.compras.sucursal_id IS ''Sucursal asociada a la compra (FK sucursales.id).''';
    END IF;
END $$;

-- 7) RLS enablement for new tables (policies to be defined separately)
ALTER TABLE public.sucursales ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.usuarios_sucursales ENABLE ROW LEVEL SECURITY;

-- Note: Run scripts/add_branch_aware_rls_policies.sql after this migration to apply branch-aware policies to ventas/venta_detalle/compras.