-- =====================================================
-- Migration 06: Create Automatic Main Branch Trigger
-- =====================================================
-- Description: Creates trigger to automatically create a main branch when a new negocio is created
-- Author: Database Migration Script
-- Date: 2025-01-20
-- =====================================================

-- =====================================================
-- SECTION 1: Function to create main branch
-- =====================================================

CREATE OR REPLACE FUNCTION create_main_sucursal_for_negocio()
RETURNS TRIGGER AS $$
DECLARE
    v_sucursal_id UUID;
BEGIN
    -- Create the main branch for the new negocio
    INSERT INTO public.sucursales (
        negocio_id,
        nombre,
        codigo,
        direccion,
        telefono,
        email,
        is_main,
        estado,
        configuracion,
        created_at,
        updated_at
    ) VALUES (
        NEW.id,
        COALESCE(NEW.nombre || ' - Principal', 'Sucursal Principal'),
        'MAIN',
        NEW.direccion,
        NEW.telefono,
        NEW.email,
        TRUE,
        'activa',
        jsonb_build_object(
            'auto_created', true,
            'created_by_trigger', true,
            'creation_date', NOW()
        ),
        NOW(),
        NOW()
    )
    RETURNING id INTO v_sucursal_id;

    RAISE NOTICE 'Created main branch (id: %) for negocio: % (%)', 
        v_sucursal_id, NEW.nombre, NEW.id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- SECTION 2: Create trigger on negocios table
-- =====================================================

DROP TRIGGER IF EXISTS trigger_create_main_sucursal ON public.negocios;

CREATE TRIGGER trigger_create_main_sucursal
    AFTER INSERT ON public.negocios
    FOR EACH ROW
    EXECUTE FUNCTION create_main_sucursal_for_negocio();

-- =====================================================
-- SECTION 3: Function to validate at least one main branch exists
-- =====================================================

CREATE OR REPLACE FUNCTION validate_main_sucursal_exists()
RETURNS TRIGGER AS $$
DECLARE
    v_main_count INTEGER;
BEGIN
    -- Allow cascade deletes from negocio removal
    IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
        RETURN OLD;
    END IF;

    -- When deleting or updating a main branch, ensure at least one remains
    IF TG_OP = 'DELETE' OR (TG_OP = 'UPDATE' AND OLD.is_main = TRUE AND NEW.is_main = FALSE) THEN
        SELECT COUNT(*) INTO v_main_count
        FROM public.sucursales
        WHERE negocio_id = OLD.negocio_id
        AND is_main = TRUE
        AND id != OLD.id;

        IF v_main_count = 0 THEN
            RAISE EXCEPTION 'Cannot remove the last main branch. Each negocio must have at least one main branch.';
        END IF;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    ELSE
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- SECTION 4: Create validation trigger
-- =====================================================

DROP TRIGGER IF EXISTS trigger_validate_main_sucursal ON public.sucursales;

CREATE TRIGGER trigger_validate_main_sucursal
    BEFORE UPDATE OR DELETE ON public.sucursales
    FOR EACH ROW
    WHEN (OLD.is_main = TRUE)
    EXECUTE FUNCTION validate_main_sucursal_exists();

-- =====================================================
-- SECTION 5: Function to auto-assign negocio owner to main branch
-- =====================================================

CREATE OR REPLACE FUNCTION assign_owner_to_main_sucursal()
RETURNS TRIGGER AS $$
DECLARE
    v_main_sucursal_id UUID;
    v_owner_id UUID;
BEGIN
    -- Find the main branch for this negocio
    SELECT id INTO v_main_sucursal_id
    FROM public.sucursales
    WHERE negocio_id = NEW.negocio_id
    AND is_main = TRUE
    LIMIT 1;

    -- If a main branch exists and the user is the owner (has negocio_id set)
    IF v_main_sucursal_id IS NOT NULL AND NEW.negocio_id IS NOT NULL THEN
        -- Check if the user is already assigned to this branch
        IF NOT EXISTS (
            SELECT 1 FROM public.usuarios_sucursales
            WHERE usuario_id = NEW.id
            AND sucursal_id = v_main_sucursal_id
        ) THEN
            -- Assign the user to the main branch
            INSERT INTO public.usuarios_sucursales (
                usuario_id,
                sucursal_id,
                negocio_id,
                rol_sucursal,
                activo,
                creado_en
            ) VALUES (
                NEW.id,
                v_main_sucursal_id,
                NEW.negocio_id,
                'administrador',
                TRUE,
                NOW()
            );

            RAISE NOTICE 'Assigned user % to main branch %', NEW.id, v_main_sucursal_id;
        END IF;

        -- Set default sucursal_id for the user if missing
        IF NEW.sucursal_id IS NULL THEN
            UPDATE public.usuarios
            SET sucursal_id = v_main_sucursal_id
            WHERE id = NEW.id;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- SECTION 6: Create trigger to assign owner to main branch
-- =====================================================

DROP TRIGGER IF EXISTS trigger_assign_owner_to_main_sucursal ON public.usuarios;

CREATE TRIGGER trigger_assign_owner_to_main_sucursal
    AFTER INSERT ON public.usuarios
    FOR EACH ROW
    WHEN (NEW.negocio_id IS NOT NULL)
    EXECUTE FUNCTION assign_owner_to_main_sucursal();

-- =====================================================
-- SECTION 7: Function to ensure negocio has at least one sucursal
-- =====================================================

CREATE OR REPLACE FUNCTION ensure_negocio_has_sucursal()
RETURNS TRIGGER AS $$
DECLARE
    v_sucursal_count INTEGER;
    v_sucursal_id UUID;
BEGIN
    -- Count existing sucursales for this negocio
    SELECT COUNT(*) INTO v_sucursal_count
    FROM public.sucursales
    WHERE negocio_id = NEW.id;

    -- If no sucursales exist, create a main one
    IF v_sucursal_count = 0 THEN
        INSERT INTO public.sucursales (
            negocio_id,
            nombre,
            codigo,
            direccion,
            telefono,
            email,
            is_main,
            estado,
            configuracion,
            created_at,
            updated_at
        ) VALUES (
            NEW.id,
            COALESCE(NEW.nombre || ' - Principal', 'Sucursal Principal'),
            'MAIN',
            NEW.direccion,
            NEW.telefono,
            NEW.email,
            TRUE,
            'activa',
            jsonb_build_object(
                'auto_created', true,
                'created_by_ensure_trigger', true,
                'creation_date', NOW()
            ),
            NOW(),
            NOW()
        )
        RETURNING id INTO v_sucursal_id;

        RAISE NOTICE 'Ensured main branch exists (id: %) for negocio: %', v_sucursal_id, NEW.id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- SECTION 8: Create trigger to ensure sucursal exists
-- =====================================================

DROP TRIGGER IF EXISTS trigger_ensure_negocio_has_sucursal ON public.negocios;

CREATE TRIGGER trigger_ensure_negocio_has_sucursal
    AFTER UPDATE ON public.negocios
    FOR EACH ROW
    EXECUTE FUNCTION ensure_negocio_has_sucursal();

-- =====================================================
-- SECTION 9: Backfill - Create main branches for existing negocios
-- =====================================================

DO $$
DECLARE
    v_negocio RECORD;
    v_sucursal_count INTEGER;
    v_sucursal_id UUID;
BEGIN
    -- Loop through all negocios
    FOR v_negocio IN 
        SELECT id, nombre, direccion, telefono, email 
        FROM public.negocios
    LOOP
        -- Check if this negocio has any sucursales
        SELECT COUNT(*) INTO v_sucursal_count
        FROM public.sucursales
        WHERE negocio_id = v_negocio.id;

        -- If no sucursales exist, create a main one
        IF v_sucursal_count = 0 THEN
            INSERT INTO public.sucursales (
                negocio_id,
                nombre,
                codigo,
                direccion,
                telefono,
                email,
                is_main,
                estado,
                configuracion,
                created_at,
                updated_at
            ) VALUES (
                v_negocio.id,
                COALESCE(v_negocio.nombre || ' - Principal', 'Sucursal Principal'),
                'MAIN',
                v_negocio.direccion,
                v_negocio.telefono,
                v_negocio.email,
                TRUE,
                'activa',
                jsonb_build_object(
                    'auto_created', true,
                    'created_by_backfill', true,
                    'creation_date', NOW()
                ),
                NOW(),
                NOW()
            )
            RETURNING id INTO v_sucursal_id;

            RAISE NOTICE 'Backfilled main branch (id: %) for existing negocio: % (%)', 
                v_sucursal_id, v_negocio.nombre, v_negocio.id;
        ELSE
            -- Check if at least one is marked as main
            SELECT COUNT(*) INTO v_sucursal_count
            FROM public.sucursales
            WHERE negocio_id = v_negocio.id
            AND is_main = TRUE;

            -- If no main branch exists, mark the first one as main
            IF v_sucursal_count = 0 THEN
                UPDATE public.sucursales
                SET is_main = TRUE
                WHERE id = (
                    SELECT id FROM public.sucursales
                    WHERE negocio_id = v_negocio.id
                    ORDER BY created_at ASC
                    LIMIT 1
                );

                RAISE NOTICE 'Marked first branch as main for negocio: % (%)', 
                    v_negocio.nombre, v_negocio.id;
            END IF;
        END IF;
    END LOOP;
END $$;

-- =====================================================
-- Summary
-- =====================================================
DO $$
BEGIN
    RAISE NOTICE '==============================================';
    RAISE NOTICE 'Migration 06 completed successfully';
    RAISE NOTICE 'Created triggers for:';
    RAISE NOTICE '  - Auto-create main branch on negocio insert';
    RAISE NOTICE '  - Validate at least one main branch exists';
    RAISE NOTICE '  - Auto-assign owner to main branch';
    RAISE NOTICE '  - Ensure negocio has at least one sucursal';
    RAISE NOTICE 'Backfilled main branches for existing negocios';
    RAISE NOTICE '==============================================';
END $$;
