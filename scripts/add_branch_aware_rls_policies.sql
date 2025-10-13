-- Branch-aware RLS policies for ventas, venta_detalle (and compras if present)
-- This script is idempotent and SAFE to run before the branch schema migration.
-- It will NO-OP until both:
--   1) ventas.sucursal_id column exists
--   2) usuarios_sucursales table exists
--
-- When those exist, it will:
--   - Recreate ventas and venta_detalle RLS policies to enforce both negocio (business) and sucursal (branch) membership for writes
--   - Keep business-level read for ventas (strict) until consolidated-view permissions are introduced
--   - Apply the same pattern to compras if the table with sucursal_id exists

DO $$
DECLARE
    has_branch_col_ventas boolean;
    has_table_user_branch  boolean;
    has_table_compras      boolean;
    has_branch_col_compras boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'ventas' AND column_name = 'sucursal_id'
    ) INTO has_branch_col_ventas;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'usuarios_sucursales'
    ) INTO has_table_user_branch;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'compras'
    ) INTO has_table_compras;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'compras' AND column_name = 'sucursal_id'
    ) INTO has_branch_col_compras;

    IF NOT has_branch_col_ventas OR NOT has_table_user_branch THEN
        RAISE NOTICE 'Skipping branch-aware RLS: ventas.sucursal_id (%), usuarios_sucursales table (%).',
            has_branch_col_ventas, has_table_user_branch;
        RETURN;
    END IF;

    -- Ensure RLS enabled (idempotent; ventas/venta_detalle should already have it)
    EXECUTE 'ALTER TABLE public.ventas ENABLE ROW LEVEL SECURITY';
    EXECUTE 'ALTER TABLE public.venta_detalle ENABLE ROW LEVEL SECURITY';

    ----------------------------------------------------------------------
    -- ventas: drop existing policies and recreate with branch-aware writes
    ----------------------------------------------------------------------
    EXECUTE 'DROP POLICY IF EXISTS "Users can view sales from their businesses" ON public.ventas';
    EXECUTE 'DROP POLICY IF EXISTS "Users can create sales in their businesses" ON public.ventas';
    EXECUTE 'DROP POLICY IF EXISTS "Users can update sales from their businesses" ON public.ventas';
    EXECUTE 'DROP POLICY IF EXISTS "Users can delete sales from their businesses" ON public.ventas';

    -- View: negocio-scoped read (strict for now; consolidated views come later)
    EXECUTE $SQL$
    CREATE POLICY "Users can view sales from their businesses" ON public.ventas
        FOR SELECT USING (
            negocio_id IN (
                SELECT un.negocio_id
                FROM public.usuarios_negocios un
                WHERE un.usuario_id = auth.uid()
            )
        );
    $SQL$;

    -- Create: require negocio membership AND branch assignment
    EXECUTE $SQL$
    CREATE POLICY "Users can create sales in their businesses" ON public.ventas
        FOR INSERT WITH CHECK (
            negocio_id IN (
                SELECT un.negocio_id
                FROM public.usuarios_negocios un
                WHERE un.usuario_id = auth.uid()
            )
            AND EXISTS (
                SELECT 1
                FROM public.usuarios_sucursales us
                WHERE us.usuario_id = auth.uid()
                  AND us.negocio_id = negocio_id
                  AND us.sucursal_id = sucursal_id
                  AND COALESCE(us.activo, true) = true
            )
        );
    $SQL$;

    -- Update: restrict to rows/user branch assignment (USING) and new values (WITH CHECK)
    EXECUTE $SQL$
    CREATE POLICY "Users can update sales from their businesses" ON public.ventas
        FOR UPDATE
        USING (
            negocio_id IN (
                SELECT un.negocio_id
                FROM public.usuarios_negocios un
                WHERE un.usuario_id = auth.uid()
            )
            AND EXISTS (
                SELECT 1
                FROM public.usuarios_sucursales us
                WHERE us.usuario_id = auth.uid()
                  AND us.negocio_id = negocio_id
                  AND us.sucursal_id = sucursal_id
                  AND COALESCE(us.activo, true) = true
            )
        )
        WITH CHECK (
            negocio_id IN (
                SELECT un.negocio_id
                FROM public.usuarios_negocios un
                WHERE un.usuario_id = auth.uid()
            )
            AND EXISTS (
                SELECT 1
                FROM public.usuarios_sucursales us
                WHERE us.usuario_id = auth.uid()
                  AND us.negocio_id = negocio_id
                  AND us.sucursal_id = sucursal_id
                  AND COALESCE(us.activo, true) = true
            )
        );
    $SQL$;

    -- Delete: restrict to user branch assignment
    EXECUTE $SQL$
    CREATE POLICY "Users can delete sales from their businesses" ON public.ventas
        FOR DELETE USING (
            negocio_id IN (
                SELECT un.negocio_id
                FROM public.usuarios_negocios un
                WHERE un.usuario_id = auth.uid()
            )
            AND EXISTS (
                SELECT 1
                FROM public.usuarios_sucursales us
                WHERE us.usuario_id = auth.uid()
                  AND us.negocio_id = negocio_id
                  AND us.sucursal_id = sucursal_id
                  AND COALESCE(us.activo, true) = true
            )
        );
    $SQL$;

    ----------------------------------------------------------------------
    -- venta_detalle: branch-aware through ventas join
    ----------------------------------------------------------------------
    EXECUTE 'DROP POLICY IF EXISTS "Users can view sale details from their businesses" ON public.venta_detalle';
    EXECUTE 'DROP POLICY IF EXISTS "Users can create sale details in their businesses" ON public.venta_detalle';
    EXECUTE 'DROP POLICY IF EXISTS "Users can update sale details from their businesses" ON public.venta_detalle';
    EXECUTE 'DROP POLICY IF EXISTS "Users can delete sale details from their businesses" ON public.venta_detalle';

    -- View: negocio membership via join to ventas
    EXECUTE $SQL$
    CREATE POLICY "Users can view sale details from their businesses" ON public.venta_detalle
        FOR SELECT USING (
            venta_id IN (
                SELECT v.id
                FROM public.ventas v
                WHERE v.negocio_id IN (
                    SELECT un.negocio_id
                    FROM public.usuarios_negocios un
                    WHERE un.usuario_id = auth.uid()
                )
            )
        );
    $SQL$;

    -- Create: require negocio membership AND branch assignment of the parent venta
    EXECUTE $SQL$
    CREATE POLICY "Users can create sale details in their businesses" ON public.venta_detalle
        FOR INSERT WITH CHECK (
            venta_id IN (
                SELECT v.id
                FROM public.ventas v
                WHERE v.negocio_id IN (
                    SELECT un.negocio_id
                    FROM public.usuarios_negocios un
                    WHERE un.usuario_id = auth.uid()
                )
                AND EXISTS (
                    SELECT 1
                    FROM public.usuarios_sucursales us
                    WHERE us.usuario_id = auth.uid()
                      AND us.negocio_id = v.negocio_id
                      AND us.sucursal_id = v.sucursal_id
                      AND COALESCE(us.activo, true) = true
                )
            )
        );
    $SQL$;

    -- Update: enforce same conditions on existing row (USING) and new relation (WITH CHECK)
    EXECUTE $SQL$
    CREATE POLICY "Users can update sale details from their businesses" ON public.venta_detalle
        FOR UPDATE
        USING (
            venta_id IN (
                SELECT v.id
                FROM public.ventas v
                WHERE v.negocio_id IN (
                    SELECT un.negocio_id
                    FROM public.usuarios_negocios un
                    WHERE un.usuario_id = auth.uid()
                )
                AND EXISTS (
                    SELECT 1
                    FROM public.usuarios_sucursales us
                    WHERE us.usuario_id = auth.uid()
                      AND us.negocio_id = v.negocio_id
                      AND us.sucursal_id = v.sucursal_id
                      AND COALESCE(us.activo, true) = true
                )
            )
        )
        WITH CHECK (
            venta_id IN (
                SELECT v.id
                FROM public.ventas v
                WHERE v.negocio_id IN (
                    SELECT un.negocio_id
                    FROM public.usuarios_negocios un
                    WHERE un.usuario_id = auth.uid()
                )
                AND EXISTS (
                    SELECT 1
                    FROM public.usuarios_sucursales us
                    WHERE us.usuario_id = auth.uid()
                      AND us.negocio_id = v.negocio_id
                      AND us.sucursal_id = v.sucursal_id
                      AND COALESCE(us.activo, true) = true
                )
            )
        );
    $SQL$;

    -- Delete: enforce branch assignment of parent venta
    EXECUTE $SQL$
    CREATE POLICY "Users can delete sale details from their businesses" ON public.venta_detalle
        FOR DELETE USING (
            venta_id IN (
                SELECT v.id
                FROM public.ventas v
                WHERE v.negocio_id IN (
                    SELECT un.negocio_id
                    FROM public.usuarios_negocios un
                    WHERE un.usuario_id = auth.uid()
                )
                AND EXISTS (
                    SELECT 1
                    FROM public.usuarios_sucursales us
                    WHERE us.usuario_id = auth.uid()
                      AND us.negocio_id = v.negocio_id
                      AND us.sucursal_id = v.sucursal_id
                      AND COALESCE(us.activo, true) = true
                )
            )
        );
    $SQL$;

    ----------------------------------------------------------------------
    -- compras (optional): apply same pattern if table and sucursal_id exist
    ----------------------------------------------------------------------
    IF has_table_compras AND has_branch_col_compras THEN
        EXECUTE 'ALTER TABLE public.compras ENABLE ROW LEVEL SECURITY';

        EXECUTE 'DROP POLICY IF EXISTS "Users can view purchases from their businesses" ON public.compras';
        EXECUTE 'DROP POLICY IF EXISTS "Users can create purchases in their businesses" ON public.compras';
        EXECUTE 'DROP POLICY IF EXISTS "Users can update purchases from their businesses" ON public.compras';
        EXECUTE 'DROP POLICY IF EXISTS "Users can delete purchases from their businesses" ON public.compras';

        -- View
        EXECUTE $SQL$
        CREATE POLICY "Users can view purchases from their businesses" ON public.compras
            FOR SELECT USING (
                negocio_id IN (
                    SELECT un.negocio_id
                    FROM public.usuarios_negocios un
                    WHERE un.usuario_id = auth.uid()
                )
            );
        $SQL$;

        -- Create
        EXECUTE $SQL$
        CREATE POLICY "Users can create purchases in their businesses" ON public.compras
            FOR INSERT WITH CHECK (
                negocio_id IN (
                    SELECT un.negocio_id
                    FROM public.usuarios_negocios un
                    WHERE un.usuario_id = auth.uid()
                )
                AND EXISTS (
                    SELECT 1
                    FROM public.usuarios_sucursales us
                    WHERE us.usuario_id = auth.uid()
                      AND us.negocio_id = negocio_id
                      AND us.sucursal_id = sucursal_id
                      AND COALESCE(us.activo, true) = true
                )
            );
        $SQL$;

        -- Update
        EXECUTE $SQL$
        CREATE POLICY "Users can update purchases from their businesses" ON public.compras
            FOR UPDATE
            USING (
                negocio_id IN (
                    SELECT un.negocio_id
                    FROM public.usuarios_negocios un
                    WHERE un.usuario_id = auth.uid()
                )
                AND EXISTS (
                    SELECT 1
                    FROM public.usuarios_sucursales us
                    WHERE us.usuario_id = auth.uid()
                      AND us.negocio_id = negocio_id
                      AND us.sucursal_id = sucursal_id
                      AND COALESCE(us.activo, true) = true
                )
            )
            WITH CHECK (
                negocio_id IN (
                    SELECT un.negocio_id
                    FROM public.usuarios_negocios un
                    WHERE un.usuario_id = auth.uid()
                )
                AND EXISTS (
                    SELECT 1
                    FROM public.usuarios_sucursales us
                    WHERE us.usuario_id = auth.uid()
                      AND us.negocio_id = negocio_id
                      AND us.sucursal_id = sucursal_id
                      AND COALESCE(us.activo, true) = true
                )
            );
        $SQL$;

        -- Delete
        EXECUTE $SQL$
        CREATE POLICY "Users can delete purchases from their businesses" ON public.compras
            FOR DELETE USING (
                negocio_id IN (
                    SELECT un.negocio_id
                    FROM public.usuarios_negocios un
                    WHERE un.usuario_id = auth.uid()
                )
                AND EXISTS (
                    SELECT 1
                    FROM public.usuarios_sucursales us
                    WHERE us.usuario_id = auth.uid()
                      AND us.negocio_id = negocio_id
                      AND us.sucursal_id = sucursal_id
                      AND COALESCE(us.activo, true) = true
                )
            );
        $SQL$;
    ELSE
        RAISE NOTICE 'Skipping compras branch-aware RLS: compras table (%), compras.sucursal_id (%).',
            has_table_compras, has_branch_col_compras;
    END IF;

    RAISE NOTICE 'Branch-aware RLS policies applied for ventas/venta_detalle (and compras if available).';
END $$;