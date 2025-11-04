-- =======================================================================================
-- Migration 08a: Structural objects for multi-branch catalog + inventory modes
-- Context     : Extends the multi-empresa initiative by introducing configuration
--               tables, per-branch catalog bridges, centralised inventory storage and
--               stock transfer records.
-- Safe to run : Yes. All DDL includes IF NOT EXISTS guards and idempotent checks.
-- =======================================================================================

SET search_path TO public;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------------------
-- negocio_configuracion: 1:1 preferences per business
-- ---------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.negocio_configuracion (
    negocio_id UUID PRIMARY KEY REFERENCES public.negocios (id) ON DELETE CASCADE,
    inventario_modo TEXT NOT NULL DEFAULT 'por_sucursal'
        CHECK (inventario_modo IN ('centralizado', 'por_sucursal')),
    servicios_modo TEXT NOT NULL DEFAULT 'por_sucursal'
        CHECK (servicios_modo IN ('centralizado', 'por_sucursal')),
    catalogo_producto_modo TEXT NOT NULL DEFAULT 'por_sucursal'
        CHECK (catalogo_producto_modo IN ('compartido', 'por_sucursal')),
    permite_transferencias BOOLEAN NOT NULL DEFAULT TRUE,
    transferencia_auto_confirma BOOLEAN NOT NULL DEFAULT FALSE,
    default_branch_id UUID NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.negocio_configuracion
    ADD CONSTRAINT negocio_configuracion_default_branch_fk
    FOREIGN KEY (default_branch_id) REFERENCES public.sucursales (id)
    ON DELETE SET NULL
    DEFERRABLE INITIALLY IMMEDIATE;

CREATE INDEX IF NOT EXISTS idx_negocio_configuracion_negocio_inventario_modo
    ON public.negocio_configuracion (negocio_id, inventario_modo);

CREATE INDEX IF NOT EXISTS idx_negocio_configuracion_negocio_catalogo_modo
    ON public.negocio_configuracion (negocio_id, catalogo_producto_modo);

-- ---------------------------------------------------------------------------------------
-- producto_sucursal: bridge between catalog and branches
-- ---------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.producto_sucursal (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    negocio_id UUID NOT NULL REFERENCES public.negocios (id) ON DELETE CASCADE,
    sucursal_id UUID NOT NULL REFERENCES public.sucursales (id) ON DELETE CASCADE,
    producto_id UUID NOT NULL REFERENCES public.productos (id) ON DELETE CASCADE,
    precio NUMERIC(18, 2) NULL,
    precio_costo NUMERIC(18, 2) NULL,
    sku_local TEXT NULL,
    stock_minimo NUMERIC(18, 2) NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'activo',
    visibilidad TEXT NOT NULL DEFAULT 'publico',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.producto_sucursal
    ADD CONSTRAINT producto_sucursal_unique_product_branch
    UNIQUE (producto_id, sucursal_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_producto_sucursal_unique_sku
    ON public.producto_sucursal (negocio_id, sucursal_id, lower(sku_local))
    WHERE sku_local IS NOT NULL AND sku_local <> '';

CREATE INDEX IF NOT EXISTS idx_producto_sucursal_negocio_branch_product
    ON public.producto_sucursal (negocio_id, sucursal_id, producto_id);

-- ---------------------------------------------------------------------------------------
-- servicio_sucursal: bridge between services and branches
-- ---------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.servicio_sucursal (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    negocio_id UUID NOT NULL REFERENCES public.negocios (id) ON DELETE CASCADE,
    sucursal_id UUID NOT NULL REFERENCES public.sucursales (id) ON DELETE CASCADE,
    servicio_id UUID NOT NULL REFERENCES public.servicios (id) ON DELETE CASCADE,
    precio NUMERIC(18, 2) NULL,
    estado TEXT NOT NULL DEFAULT 'activo',
    visibilidad TEXT NOT NULL DEFAULT 'publico',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.servicio_sucursal
    ADD CONSTRAINT servicio_sucursal_unique_service_branch
    UNIQUE (servicio_id, sucursal_id);

CREATE INDEX IF NOT EXISTS idx_servicio_sucursal_negocio_branch_service
    ON public.servicio_sucursal (negocio_id, sucursal_id, servicio_id);

-- ---------------------------------------------------------------------------------------
-- inventario_negocio: aggregated inventory per business/product
-- ---------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.inventario_negocio (
    negocio_id UUID NOT NULL REFERENCES public.negocios (id) ON DELETE CASCADE,
    producto_id UUID NOT NULL REFERENCES public.productos (id) ON DELETE CASCADE,
    stock_total NUMERIC(18, 2) NOT NULL DEFAULT 0,
    reservado NUMERIC(18, 2) NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (negocio_id, producto_id)
);

CREATE INDEX IF NOT EXISTS idx_inventario_negocio_negocio_producto
    ON public.inventario_negocio (negocio_id, producto_id);

-- ---------------------------------------------------------------------------------------
-- stock_transferencias: transfer headers
-- ---------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.stock_transferencias (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    negocio_id UUID NOT NULL REFERENCES public.negocios (id) ON DELETE CASCADE,
    origen_sucursal_id UUID NOT NULL REFERENCES public.sucursales (id) ON DELETE CASCADE,
    destino_sucursal_id UUID NOT NULL REFERENCES public.sucursales (id) ON DELETE CASCADE,
    estado TEXT NOT NULL DEFAULT 'borrador'
        CHECK (estado IN ('borrador', 'confirmada', 'cancelada', 'recibida')),
    inventario_modo_source TEXT NULL,
    inventario_modo_target TEXT NULL,
    permite_transferencias_snapshot BOOLEAN NULL,
    creado_por UUID NOT NULL REFERENCES auth.users (id),
    aprobado_por UUID NULL REFERENCES auth.users (id),
    comentarios TEXT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT stock_transferencias_origen_destino_diff CHECK (origen_sucursal_id <> destino_sucursal_id)
);

CREATE INDEX IF NOT EXISTS idx_stock_transferencias_negocio_estado
    ON public.stock_transferencias (negocio_id, estado, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_stock_transferencias_origen_destino
    ON public.stock_transferencias (origen_sucursal_id, destino_sucursal_id);

-- ---------------------------------------------------------------------------------------
-- stock_transferencias_detalle: transfer line items
-- ---------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.stock_transferencias_detalle (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transferencia_id UUID NOT NULL REFERENCES public.stock_transferencias (id) ON DELETE CASCADE,
    negocio_id UUID NOT NULL REFERENCES public.negocios (id) ON DELETE CASCADE,
    producto_id UUID NOT NULL REFERENCES public.productos (id) ON DELETE CASCADE,
    cantidad NUMERIC(18, 2) NOT NULL CHECK (cantidad > 0),
    unidad TEXT NULL,
    lote TEXT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stock_transferencias_detalle_transferencia
    ON public.stock_transferencias_detalle (transferencia_id);

CREATE INDEX IF NOT EXISTS idx_stock_transferencias_detalle_negocio_producto
    ON public.stock_transferencias_detalle (negocio_id, producto_id);

-- ---------------------------------------------------------------------------------------
-- inventario_visible: view that adapts to the configured inventory mode
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.vw_inventario_visible AS
WITH cfg AS (
    SELECT negocio_id,
           inventario_modo
    FROM public.negocio_configuracion
)
SELECT
    isur.negocio_id,
    isur.sucursal_id,
    isur.producto_id,
    CASE
        WHEN cfg.inventario_modo = 'centralizado'
            THEN COALESCE(invneg.stock_total, isur.stock_actual)
        ELSE isur.stock_actual
    END AS stock_disponible,
    isur.stock_actual AS stock_sucursal,
    COALESCE(invneg.stock_total, 0) AS stock_negocio,
    cfg.inventario_modo,
    isur.updated_at AS inventario_actualizado_en
FROM public.inventario_sucursal AS isur
JOIN cfg ON cfg.negocio_id = isur.negocio_id
LEFT JOIN public.inventario_negocio AS invneg
       ON invneg.negocio_id = isur.negocio_id
      AND invneg.producto_id = isur.producto_id;

-- ---------------------------------------------------------------------------------------
-- Trigger helpers
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.fn_ensure_negocio_configuracion()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO public.negocio_configuracion (negocio_id, default_branch_id)
    VALUES (NEW.id, NULL)
    ON CONFLICT (negocio_id) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_negocio_configuracion_autocreate ON public.negocios;
CREATE TRIGGER trg_negocio_configuracion_autocreate
    AFTER INSERT ON public.negocios
    FOR EACH ROW
    EXECUTE FUNCTION public.fn_ensure_negocio_configuracion();

CREATE OR REPLACE FUNCTION public.fn_sync_branch_on_insert()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    cfg RECORD;
BEGIN
    SELECT *
      INTO cfg
      FROM public.negocio_configuracion
     WHERE negocio_id = NEW.negocio_id
     LIMIT 1;

    IF cfg IS NULL THEN
        INSERT INTO public.negocio_configuracion (negocio_id, default_branch_id)
        VALUES (NEW.negocio_id, NULL)
        ON CONFLICT (negocio_id) DO NOTHING;
        SELECT *
          INTO cfg
          FROM public.negocio_configuracion
         WHERE negocio_id = NEW.negocio_id
         LIMIT 1;
    END IF;

    IF NEW.is_main IS TRUE THEN
        UPDATE public.negocio_configuracion
           SET default_branch_id = NEW.id,
               updated_at = NOW()
         WHERE negocio_id = NEW.negocio_id
           AND (default_branch_id IS DISTINCT FROM NEW.id);
    END IF;

    IF cfg.catalogo_producto_modo = 'compartido' THEN
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
            NEW.id,
            p.id,
            p.precio,
            p.precio_costo,
            NULLIF(p.sku, ''),
            COALESCE(p.stock_minimo, 0),
            COALESCE(p.estado, 'activo'),
            COALESCE(p.visibilidad, 'publico'),
            COALESCE(p.metadata, '{}'::jsonb) || jsonb_build_object('source', 'fn_sync_branch_on_insert'),
            NOW(),
            NOW()
        FROM public.productos AS p
        WHERE p.negocio_id = NEW.negocio_id
        ON CONFLICT (producto_id, sucursal_id) DO NOTHING;

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
            s.negocio_id,
            NEW.id,
            s.id,
            s.precio,
            COALESCE(s.estado, 'activo'),
            COALESCE(s.visibilidad, 'publico'),
            COALESCE(s.metadata, '{}'::jsonb) || jsonb_build_object('source', 'fn_sync_branch_on_insert'),
            NOW(),
            NOW()
        FROM public.servicios AS s
        WHERE s.negocio_id = NEW.negocio_id
        ON CONFLICT (servicio_id, sucursal_id) DO NOTHING;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sync_branch_on_insert ON public.sucursales;
CREATE TRIGGER trg_sync_branch_on_insert
    AFTER INSERT ON public.sucursales
    FOR EACH ROW
    EXECUTE FUNCTION public.fn_sync_branch_on_insert();

-- ---------------------------------------------------------------------------------------
-- Generic updated_at trigger bindings
-- ---------------------------------------------------------------------------------------
CREATE TRIGGER trg_negocio_configuracion_updated_at
    BEFORE UPDATE ON public.negocio_configuracion
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER trg_producto_sucursal_updated_at
    BEFORE UPDATE ON public.producto_sucursal
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER trg_servicio_sucursal_updated_at
    BEFORE UPDATE ON public.servicio_sucursal
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER trg_inventario_negocio_updated_at
    BEFORE UPDATE ON public.inventario_negocio
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER trg_stock_transferencias_updated_at
    BEFORE UPDATE ON public.stock_transferencias
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER trg_stock_transferencias_detalle_updated_at
    BEFORE UPDATE ON public.stock_transferencias_detalle
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

-- ---------------------------------------------------------------------------------------
-- Helper function to expose configuration via SQL
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.fn_get_branch_settings(p_negocio_id UUID)
RETURNS TABLE (
    negocio_id UUID,
    inventario_modo TEXT,
    servicios_modo TEXT,
    catalogo_producto_modo TEXT,
    permite_transferencias BOOLEAN,
    transferencia_auto_confirma BOOLEAN,
    default_branch_id UUID,
    metadata JSONB,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
)
LANGUAGE sql
AS $$
    SELECT
        nc.negocio_id,
        nc.inventario_modo,
        nc.servicios_modo,
        nc.catalogo_producto_modo,
        nc.permite_transferencias,
        nc.transferencia_auto_confirma,
        nc.default_branch_id,
        nc.metadata,
        nc.created_at,
        nc.updated_at
    FROM public.negocio_configuracion AS nc
    WHERE nc.negocio_id = p_negocio_id;
$$;

DO $$
BEGIN
    RAISE NOTICE 'migration_08a_create_branch_mode_structures executed.';
END;
$$;
