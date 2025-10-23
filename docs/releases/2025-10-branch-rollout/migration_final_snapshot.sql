-- =====================================================
-- Migration 07: Revisar y actualizar politicas RLS multi-negocio
-- =====================================================
-- Objetivo:
--   * Consolidar las politicas de RLS para tablas con datos sensibles
--   * Asegurar filtrado por negocio_id y sucursal_id (cuando corresponda)
--   * Homologar la logica de acceso usando funciones auxiliares seguras
--   * Verificar compatibilidad con el contexto actual (`auth.uid()` y claims JWT)
--
-- Idempotencia: seguro de re-ejecutar. Todas las funciones/politicas se crean
--               con CREATE OR REPLACE y se eliminan las versiones previas.
-- Dependencias: requiere tablas `usuarios_negocios` y (opcional) `usuarios_sucursales`
--               para resolver el contexto de pertenencia a negocio/sucursal.
-- =====================================================

-- =====================================================
-- Seccion 1: Funciones auxiliares de contexto (idempotentes)
-- =====================================================

CREATE OR REPLACE FUNCTION public.jwt_claim_negocio_id()
RETURNS uuid
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    claims jsonb;
    claim_txt text;
BEGIN
    BEGIN
        claims := current_setting('request.jwt.claims', true)::jsonb;
    EXCEPTION
        WHEN others THEN
            RETURN NULL;
    END;

    IF claims ? 'negocio_id' THEN
        claim_txt := claims->>'negocio_id';
        BEGIN
            RETURN claim_txt::uuid;
        EXCEPTION
            WHEN others THEN
                RETURN NULL;
        END;
    END IF;

    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION public.jwt_claim_negocio_id() IS
    'Obtiene el negocio_id actual desde los claims JWT (request.jwt.claims). Retorna NULL si no existe o no es UUID.';


CREATE OR REPLACE FUNCTION public.jwt_negocio_matches(target_negocio_id uuid)
RETURNS boolean
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    claim_negocio uuid;
BEGIN
    claim_negocio := public.jwt_claim_negocio_id();
    IF claim_negocio IS NULL THEN
        RETURN TRUE;
    END IF;
    RETURN claim_negocio = target_negocio_id;
END;
$$;

COMMENT ON FUNCTION public.jwt_negocio_matches(uuid) IS
    'Valida que el negocio_id de la fila coincida con el negocio_id del JWT (si viene seteado).';


CREATE OR REPLACE FUNCTION public.user_in_business(target_negocio_id uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1
        FROM public.usuarios_negocios un
        WHERE un.negocio_id = target_negocio_id
          AND un.usuario_id = auth.uid()
          AND COALESCE(un.estado, 'aceptado') = 'aceptado'
    );
END;
$$;

COMMENT ON FUNCTION public.user_in_business(uuid) IS
    'Indica si el usuario autenticado pertenece (estado aceptado) al negocio dado.';


CREATE OR REPLACE FUNCTION public.user_is_business_admin(target_negocio_id uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1
        FROM public.usuarios_negocios un
        WHERE un.negocio_id = target_negocio_id
          AND un.usuario_id = auth.uid()
          AND COALESCE(un.estado, 'aceptado') = 'aceptado'
          AND COALESCE(un.rol, 'empleado') IN (
                'admin', 'owner', 'dueno', 'propietario', 'superadmin'
          )
    );
END;
$$;

COMMENT ON FUNCTION public.user_is_business_admin(uuid) IS
    'Retorna TRUE si el usuario autenticado tiene rol administrador dentro del negocio indicado.';


CREATE OR REPLACE FUNCTION public.user_can_access_branch(target_negocio_id uuid, target_sucursal_id uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF target_sucursal_id IS NULL THEN
        RETURN public.user_is_business_admin(target_negocio_id);
    END IF;

    IF public.user_is_business_admin(target_negocio_id) THEN
        RETURN TRUE;
    END IF;

    RETURN EXISTS (
        SELECT 1
        FROM public.usuarios_sucursales us
        WHERE us.negocio_id = target_negocio_id
          AND us.sucursal_id = target_sucursal_id
          AND us.usuario_id = auth.uid()
          AND COALESCE(us.activo, TRUE)
    );
END;
$$;

COMMENT ON FUNCTION public.user_can_access_branch(uuid, uuid) IS
    'Determina si el usuario autenticado puede operar sobre la sucursal indicada (admin o asignado/activo).';


GRANT EXECUTE ON FUNCTION public.jwt_claim_negocio_id() TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.jwt_negocio_matches(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.user_in_business(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.user_is_business_admin(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.user_can_access_branch(uuid, uuid) TO authenticated, service_role;

-- =====================================================
-- Seccion 2: Politicas especificas (negocios, usuarios_negocios, usuarios_sucursales)
-- =====================================================

DO $$
DECLARE
    policy_name text;
BEGIN
    -- NEGOCIOS ------------------------------------------------------------
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'negocios'
    ) THEN
        EXECUTE 'ALTER TABLE public.negocios ENABLE ROW LEVEL SECURITY';

        FOREACH policy_name IN ARRAY ARRAY[
            'Users can view businesses',
            'Users can update businesses',
            'Users can delete businesses',
            'Users can insert businesses',
            'rls_negocios_select',
            'rls_negocios_insert',
            'rls_negocios_update',
            'rls_negocios_delete'
        ]
        LOOP
            EXECUTE format('DROP POLICY IF EXISTS %I ON public.negocios', policy_name);
        END LOOP;

        EXECUTE $SQL$
        CREATE POLICY rls_negocios_select ON public.negocios
            FOR SELECT
            USING (
                public.user_in_business(id)
                AND public.jwt_negocio_matches(id)
            );
        $SQL$;

        EXECUTE $SQL$
        CREATE POLICY rls_negocios_insert ON public.negocios
            FOR INSERT
            WITH CHECK (
                auth.uid() IS NOT NULL
            );
        $SQL$;

        EXECUTE $SQL$
        CREATE POLICY rls_negocios_update ON public.negocios
            FOR UPDATE
            USING (
                public.user_is_business_admin(id)
                AND public.jwt_negocio_matches(id)
            )
            WITH CHECK (
                public.user_is_business_admin(id)
                AND public.jwt_negocio_matches(id)
            );
        $SQL$;

        EXECUTE $SQL$
        CREATE POLICY rls_negocios_delete ON public.negocios
            FOR DELETE
            USING (
                public.user_is_business_admin(id)
                AND public.jwt_negocio_matches(id)
            );
        $SQL$;
    ELSE
        RAISE NOTICE 'Tabla negocios no encontrada; se omite aplicacion de RLS.';
    END IF;

    -- USUARIOS_NEGOCIOS ---------------------------------------------------
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'usuarios_negocios'
    ) THEN
        EXECUTE 'ALTER TABLE public.usuarios_negocios ENABLE ROW LEVEL SECURITY';

        FOREACH policy_name IN ARRAY ARRAY[
            'usuarios_negocios_insert_policy',
            'usuarios_negocios_update_policy',
            'usuarios_negocios_invite_only_policy',
            'usuarios_negocios_admin_update_policy',
            'rls_usuarios_negocios_select',
            'rls_usuarios_negocios_insert',
            'rls_usuarios_negocios_update',
            'rls_usuarios_negocios_delete'
        ]
        LOOP
            EXECUTE format('DROP POLICY IF EXISTS %I ON public.usuarios_negocios', policy_name);
        END LOOP;

        EXECUTE $SQL$
        CREATE POLICY rls_usuarios_negocios_select ON public.usuarios_negocios
            FOR SELECT
            USING (
                usuario_id = auth.uid()
                OR public.user_is_business_admin(negocio_id)
            );
        $SQL$;

        EXECUTE $SQL$
        CREATE POLICY rls_usuarios_negocios_insert ON public.usuarios_negocios
            FOR INSERT
            WITH CHECK (
                public.user_is_business_admin(negocio_id)
            );
        $SQL$;

        EXECUTE $SQL$
        CREATE POLICY rls_usuarios_negocios_update ON public.usuarios_negocios
            FOR UPDATE
            USING (
                usuario_id = auth.uid()
                OR public.user_is_business_admin(negocio_id)
            )
            WITH CHECK (
                usuario_id = auth.uid()
                OR public.user_is_business_admin(negocio_id)
            );
        $SQL$;

        EXECUTE $SQL$
        CREATE POLICY rls_usuarios_negocios_delete ON public.usuarios_negocios
            FOR DELETE
            USING (
                public.user_is_business_admin(negocio_id)
            );
        $SQL$;
    ELSE
        RAISE NOTICE 'Tabla usuarios_negocios no encontrada; se omite aplicacion de RLS.';
    END IF;

    -- USUARIOS_SUCURSALES -------------------------------------------------
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'usuarios_sucursales'
    ) THEN
        EXECUTE 'ALTER TABLE public.usuarios_sucursales ENABLE ROW LEVEL SECURITY';

        FOREACH policy_name IN ARRAY ARRAY[
            'Users can view their own branch assignments',
            'Admins can view branch assignments in their businesses',
            'rls_usuarios_sucursales_select',
            'rls_usuarios_sucursales_insert',
            'rls_usuarios_sucursales_update',
            'rls_usuarios_sucursales_delete'
        ]
        LOOP
            EXECUTE format('DROP POLICY IF EXISTS %I ON public.usuarios_sucursales', policy_name);
        END LOOP;

        EXECUTE $SQL$
        CREATE POLICY rls_usuarios_sucursales_select ON public.usuarios_sucursales
            FOR SELECT
            USING (
                usuario_id = auth.uid()
                OR public.user_is_business_admin(negocio_id)
            );
        $SQL$;

        EXECUTE $SQL$
        CREATE POLICY rls_usuarios_sucursales_insert ON public.usuarios_sucursales
            FOR INSERT
            WITH CHECK (
                public.user_is_business_admin(negocio_id)
                OR (
                    auth.uid() = usuario_id
                    AND public.user_can_access_branch(negocio_id, sucursal_id)
                )
            );
        $SQL$;

        EXECUTE $SQL$
        CREATE POLICY rls_usuarios_sucursales_update ON public.usuarios_sucursales
            FOR UPDATE
            USING (
                usuario_id = auth.uid()
                OR public.user_is_business_admin(negocio_id)
            )
            WITH CHECK (
                usuario_id = auth.uid()
                OR public.user_is_business_admin(negocio_id)
            );
        $SQL$;

        EXECUTE $SQL$
        CREATE POLICY rls_usuarios_sucursales_delete ON public.usuarios_sucursales
            FOR DELETE
            USING (
                public.user_is_business_admin(negocio_id)
            );
        $SQL$;
    ELSE
        RAISE NOTICE 'Tabla usuarios_sucursales no encontrada; se omite aplicacion de RLS.';
    END IF;
END $$;

-- =====================================================
-- Seccion 3: Politicas para tablas de negocio (sin sucursal_id)
-- =====================================================

DO $$
DECLARE
    tbl text;
    using_condition text;
    policy text;
BEGIN
    FOR tbl IN SELECT unnest(ARRAY[
        'sucursales',
        'usuarios',
        'productos',
        'clientes',
        'proveedores',
        'servicios',
        'suscripciones'
    ])
    LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = tbl
        ) AND EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = tbl AND column_name = 'negocio_id'
        ) THEN
            EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', tbl);

            IF tbl = 'sucursales' THEN
                FOR policy IN SELECT unnest(ARRAY[
                    'Users can view branches in their businesses'
                ])
                LOOP
                    EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', policy, tbl);
                END LOOP;
            ELSIF tbl = 'servicios' THEN
                FOR policy IN SELECT unnest(ARRAY[
                    'Users can view services from their businesses',
                    'Users can insert services in their businesses',
                    'Users can update services from their businesses',
                    'Users can delete services from their businesses'
                ])
                LOOP
                    EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', policy, tbl);
                END LOOP;
            ELSIF tbl = 'suscripciones' THEN
                FOR policy IN SELECT unnest(ARRAY[
                    'Users can view subscriptions from their businesses',
                    'Users can insert subscriptions in their businesses',
                    'Users can update subscriptions from their businesses',
                    'Users can delete subscriptions from their businesses'
                ])
                LOOP
                    EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', policy, tbl);
                END LOOP;
            END IF;

            FOR policy IN SELECT unnest(ARRAY[
                'rls_' || tbl || '_select',
                'rls_' || tbl || '_insert',
                'rls_' || tbl || '_update',
                'rls_' || tbl || '_delete'
            ])
            LOOP
                EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', policy, tbl);
            END LOOP;

            IF tbl = 'usuarios' THEN
                using_condition := '(
                    (id = auth.uid())
                    OR public.user_is_business_admin(negocio_id)
                ) AND public.jwt_negocio_matches(negocio_id)';
            ELSE
                using_condition := 'public.user_in_business(negocio_id)
                    AND public.jwt_negocio_matches(negocio_id)';
            END IF;

            EXECUTE format(
                'CREATE POLICY %I ON public.%I FOR SELECT USING (%s);',
                'rls_' || tbl || '_select',
                tbl,
                using_condition
            );

            EXECUTE format(
                'CREATE POLICY %I ON public.%I FOR INSERT WITH CHECK (%s);',
                'rls_' || tbl || '_insert',
                tbl,
                CASE
                    WHEN tbl = 'usuarios'
                        THEN 'public.user_is_business_admin(negocio_id)'
                    ELSE using_condition
                END
            );

            EXECUTE format(
                'CREATE POLICY %I ON public.%I FOR UPDATE USING (%s) WITH CHECK (%s);',
                'rls_' || tbl || '_update',
                tbl,
                using_condition,
                CASE
                    WHEN tbl = 'usuarios'
                        THEN 'public.user_is_business_admin(negocio_id)'
                    ELSE using_condition
                END
            );

            EXECUTE format(
                'CREATE POLICY %I ON public.%I FOR DELETE USING (%s);',
                'rls_' || tbl || '_delete',
                tbl,
                CASE
                    WHEN tbl = 'usuarios'
                        THEN 'public.user_is_business_admin(negocio_id)'
                    ELSE using_condition
                END
            );
        ELSE
            RAISE NOTICE 'Tabla % no encontrada o sin columna negocio_id; se omite.', tbl;
        END IF;
    END LOOP;
END $$;

-- =====================================================
-- Seccion 4: Politicas para tablas con sucursal (ventas, compras, etc.)
-- =====================================================

DO $$
DECLARE
    tbl text;
    using_condition text;
    policy text;
BEGIN
    FOR tbl IN SELECT unnest(ARRAY[
        'ventas',
        'venta_detalle',
        'compras',
        'compras_detalle',
        'inventario_sucursal'
    ])
    LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = tbl
        ) AND EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = tbl AND column_name = 'negocio_id'
        ) AND EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = tbl AND column_name = 'sucursal_id'
        ) THEN
            EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', tbl);

            FOR policy IN SELECT unnest(ARRAY[
                'Users can view sales from their businesses',
                'Users can create sales in their businesses',
                'Users can update sales from their businesses',
                'Users can delete sales from their businesses',
                'Users can view sale details from their businesses',
                'Users can create sale details in their businesses',
                'Users can update sale details from their businesses',
                'Users can delete sale details from their businesses',
                'Users can view purchases from their businesses',
                'Users can create purchases in their businesses',
                'Users can update purchases from their businesses',
                'Users can delete purchases from their businesses'
            ])
            LOOP
                EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', policy, tbl);
            END LOOP;

            FOR policy IN SELECT unnest(ARRAY[
                'rls_' || tbl || '_select',
                'rls_' || tbl || '_insert',
                'rls_' || tbl || '_update',
                'rls_' || tbl || '_delete'
            ])
            LOOP
                EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', policy, tbl);
            END LOOP;

            using_condition := 'public.user_in_business(negocio_id)
                AND public.user_can_access_branch(negocio_id, sucursal_id)
                AND public.jwt_negocio_matches(negocio_id)';

            EXECUTE format(
                'CREATE POLICY %I ON public.%I FOR SELECT USING (%s);',
                'rls_' || tbl || '_select',
                tbl,
                using_condition
            );

            EXECUTE format(
                'CREATE POLICY %I ON public.%I FOR INSERT WITH CHECK (%s);',
                'rls_' || tbl || '_insert',
                tbl,
                using_condition
            );

            EXECUTE format(
                'CREATE POLICY %I ON public.%I FOR UPDATE USING (%s) WITH CHECK (%s);',
                'rls_' || tbl || '_update',
                tbl,
                using_condition,
                using_condition
            );

            EXECUTE format(
                'CREATE POLICY %I ON public.%I FOR DELETE USING (%s);',
                'rls_' || tbl || '_delete',
                tbl,
                using_condition
            );
        ELSE
            RAISE NOTICE 'Tabla % sin columnas negocio_id+sucursal_id o inexistente; se omite.', tbl;
        END IF;
    END LOOP;
END $$;

-- =====================================================
-- Resumen
-- =====================================================

DO $$
BEGIN
    RAISE NOTICE 'Politicas RLS actualizadas: funciones auxiliares creadas y tablas clave protegidas por negocio/sucursal.';
END $$;
