-- Patch for branch-aware rollout: fix ventas/venta_detalle schema gaps and add minimal RLS for branch tables
-- Safe/idempotent. Run after scripts/add_branches_and_sucursal_fk.sql

-- 1) Ensure ventas has usuario_negocio_id and estado columns
ALTER TABLE public.ventas
    ADD COLUMN IF NOT EXISTS usuario_negocio_id UUID REFERENCES public.usuarios_negocios(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_ventas_usuario_negocio_id ON public.ventas(usuario_negocio_id);

ALTER TABLE public.ventas
    ADD COLUMN IF NOT EXISTS estado TEXT DEFAULT 'completada';

CREATE INDEX IF NOT EXISTS idx_ventas_estado ON public.ventas(estado);

-- 2) Ensure venta_detalle supports services and discounts
ALTER TABLE public.venta_detalle
    ADD COLUMN IF NOT EXISTS servicio_id UUID REFERENCES public.servicios(id);

ALTER TABLE public.venta_detalle
    ADD COLUMN IF NOT EXISTS tipo VARCHAR(20) DEFAULT 'producto';

-- Add CHECK constraint for tipo values if missing
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'venta_detalle_tipo_check'
          AND conrelid = 'public.venta_detalle'::regclass
    ) THEN
        EXECUTE 'ALTER TABLE public.venta_detalle
                 ADD CONSTRAINT venta_detalle_tipo_check
                 CHECK (tipo IN (''producto'', ''servicio''))';
    END IF;
END $$;

-- Make producto_id nullable if currently NOT NULL
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'venta_detalle'
          AND column_name = 'producto_id'
          AND is_nullable = 'NO'
    ) THEN
        EXECUTE 'ALTER TABLE public.venta_detalle ALTER COLUMN producto_id DROP NOT NULL';
    END IF;
END $$;

-- Add combined product/service exclusivity constraint if missing
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'venta_detalle_producto_or_servicio_check'
          AND conrelid = 'public.venta_detalle'::regclass
    ) THEN
        EXECUTE 'ALTER TABLE public.venta_detalle
                 ADD CONSTRAINT venta_detalle_producto_or_servicio_check
                 CHECK (
                   (producto_id IS NOT NULL AND servicio_id IS NULL AND tipo = ''producto'') OR
                   (producto_id IS NULL AND servicio_id IS NOT NULL AND tipo = ''servicio'')
                 )';
    END IF;
END $$;

-- Optional discount column used by API responses
ALTER TABLE public.venta_detalle
    ADD COLUMN IF NOT EXISTS descuento NUMERIC(10,2) DEFAULT 0;

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_venta_detalle_servicio_id ON public.venta_detalle(servicio_id);
CREATE INDEX IF NOT EXISTS idx_venta_detalle_tipo ON public.venta_detalle(tipo);

-- 3) Minimal RLS policies for branch tables used by the API
DO $$
DECLARE
    has_sucursales boolean;
    has_usuarios_sucursales boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'sucursales'
    ) INTO has_sucursales;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'usuarios_sucursales'
    ) INTO has_usuarios_sucursales;

    IF has_sucursales THEN
        EXECUTE 'ALTER TABLE public.sucursales ENABLE ROW LEVEL SECURITY';

        EXECUTE 'DROP POLICY IF EXISTS "Users can view branches in their businesses" ON public.sucursales';

        EXECUTE $SQL$
        CREATE POLICY "Users can view branches in their businesses" ON public.sucursales
            FOR SELECT USING (
                negocio_id IN (
                    SELECT un.negocio_id
                    FROM public.usuarios_negocios un
                    WHERE un.usuario_id = auth.uid()
                      AND COALESCE(un.estado, 'aceptado') = 'aceptado'
                )
            );
        $SQL$;
    END IF;

    IF has_usuarios_sucursales THEN
        EXECUTE 'ALTER TABLE public.usuarios_sucursales ENABLE ROW LEVEL SECURITY';

        EXECUTE 'DROP POLICY IF EXISTS "Users can view their own branch assignments" ON public.usuarios_sucursales';
        EXECUTE 'DROP POLICY IF EXISTS "Admins can view branch assignments in their businesses" ON public.usuarios_sucursales';

        EXECUTE $SQL$
        CREATE POLICY "Users can view their own branch assignments" ON public.usuarios_sucursales
            FOR SELECT USING (
                usuario_id = auth.uid()
            );
        $SQL$;

        EXECUTE $SQL$
        CREATE POLICY "Admins can view branch assignments in their businesses" ON public.usuarios_sucursales
            FOR SELECT USING (
                negocio_id IN (
                    SELECT un.negocio_id
                    FROM public.usuarios_negocios un
                    WHERE un.usuario_id = auth.uid()
                      AND COALESCE(un.estado, 'aceptado') = 'aceptado'
                      AND COALESCE(un.rol, 'empleado') = 'admin'
                )
            );
        $SQL$;
    END IF;

    RAISE NOTICE 'Branch rollout patch applied: schema and RLS updates completed.';
END $$;

-- End of patch