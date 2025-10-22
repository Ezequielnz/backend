-- =====================================================
-- Migration 02: Verify and Update SUCURSALES Table
-- =====================================================
-- Description: Ensures the sucursales table exists with all required fields
-- Author: Database Migration Script
-- Date: 2025-01-20
-- =====================================================

-- Check if sucursales table exists, if not create it
CREATE TABLE IF NOT EXISTS public.sucursales (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    negocio_id UUID NOT NULL,
    nombre VARCHAR(255) NOT NULL,
    codigo VARCHAR(50),
    direccion TEXT,
    telefono VARCHAR(50),
    email VARCHAR(255),
    is_main BOOLEAN DEFAULT FALSE,
    estado VARCHAR(50) DEFAULT 'activa' CHECK (estado IN ('activa', 'inactiva', 'cerrada')),
    horario_apertura TIME,
    horario_cierre TIME,
    dias_operacion JSONB DEFAULT '["lunes","martes","miercoles","jueves","viernes"]',
    configuracion JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Add missing columns if they don't exist
DO $$ 
BEGIN
    -- Add negocio_id if missing (critical FK)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'sucursales' 
                   AND column_name = 'negocio_id') THEN
        ALTER TABLE public.sucursales ADD COLUMN negocio_id UUID NOT NULL;
    END IF;

    -- Add nombre if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'sucursales' 
                   AND column_name = 'nombre') THEN
        ALTER TABLE public.sucursales ADD COLUMN nombre VARCHAR(255) NOT NULL;
    END IF;

    -- Add codigo if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'sucursales' 
                   AND column_name = 'codigo') THEN
        ALTER TABLE public.sucursales ADD COLUMN codigo VARCHAR(50);
    END IF;

    -- Add direccion if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'sucursales' 
                   AND column_name = 'direccion') THEN
        ALTER TABLE public.sucursales ADD COLUMN direccion TEXT;
    END IF;

    -- Add telefono if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'sucursales' 
                   AND column_name = 'telefono') THEN
        ALTER TABLE public.sucursales ADD COLUMN telefono VARCHAR(50);
    END IF;

    -- Add email if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'sucursales' 
                   AND column_name = 'email') THEN
        ALTER TABLE public.sucursales ADD COLUMN email VARCHAR(255);
    END IF;

    -- Add is_main if missing (important for identifying main branch)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'sucursales' 
                   AND column_name = 'is_main') THEN
        ALTER TABLE public.sucursales ADD COLUMN is_main BOOLEAN DEFAULT FALSE;
    END IF;

    -- Add estado if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'sucursales' 
                   AND column_name = 'estado') THEN
        ALTER TABLE public.sucursales ADD COLUMN estado VARCHAR(50) DEFAULT 'activa';
        ALTER TABLE public.sucursales ADD CONSTRAINT sucursales_estado_check 
            CHECK (estado IN ('activa', 'inactiva', 'cerrada'));
    END IF;

    -- Add horario_apertura if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'sucursales' 
                   AND column_name = 'horario_apertura') THEN
        ALTER TABLE public.sucursales ADD COLUMN horario_apertura TIME;
    END IF;

    -- Add horario_cierre if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'sucursales' 
                   AND column_name = 'horario_cierre') THEN
        ALTER TABLE public.sucursales ADD COLUMN horario_cierre TIME;
    END IF;

    -- Add dias_operacion if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'sucursales' 
                   AND column_name = 'dias_operacion') THEN
        ALTER TABLE public.sucursales ADD COLUMN dias_operacion JSONB DEFAULT '["lunes","martes","miercoles","jueves","viernes"]';
    END IF;

    -- Add configuracion if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'sucursales' 
                   AND column_name = 'configuracion') THEN
        ALTER TABLE public.sucursales ADD COLUMN configuracion JSONB DEFAULT '{}';
    END IF;

    -- Add created_at if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'sucursales' 
                   AND column_name = 'created_at') THEN
        ALTER TABLE public.sucursales ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
    END IF;

    -- Add updated_at if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'sucursales' 
                   AND column_name = 'updated_at') THEN
        ALTER TABLE public.sucursales ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
    END IF;
END $$;

-- Add foreign key to negocios if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_sucursales_negocio_id' 
        AND table_name = 'sucursales'
    ) THEN
        ALTER TABLE public.sucursales 
        ADD CONSTRAINT fk_sucursales_negocio_id 
        FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;
    END IF;
END $$;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_sucursales_negocio_id ON public.sucursales(negocio_id);
CREATE INDEX IF NOT EXISTS idx_sucursales_estado ON public.sucursales(estado);
CREATE INDEX IF NOT EXISTS idx_sucursales_is_main ON public.sucursales(is_main);
CREATE INDEX IF NOT EXISTS idx_sucursales_codigo ON public.sucursales(codigo);

-- Create unique constraint for codigo within negocio
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'unique_sucursal_codigo_per_negocio' 
        AND table_name = 'sucursales'
    ) THEN
        ALTER TABLE public.sucursales 
        ADD CONSTRAINT unique_sucursal_codigo_per_negocio 
        UNIQUE (negocio_id, codigo);
    END IF;
END $$;

-- Create or replace trigger for updated_at
CREATE OR REPLACE FUNCTION update_sucursales_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_sucursales_updated_at ON public.sucursales;
CREATE TRIGGER trigger_sucursales_updated_at
    BEFORE UPDATE ON public.sucursales
    FOR EACH ROW
    EXECUTE FUNCTION update_sucursales_updated_at();

-- Create constraint to ensure only one main branch per negocio
CREATE OR REPLACE FUNCTION check_single_main_sucursal()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.is_main = TRUE THEN
        -- Set all other branches of this negocio to is_main = FALSE
        UPDATE public.sucursales 
        SET is_main = FALSE 
        WHERE negocio_id = NEW.negocio_id 
        AND id != NEW.id 
        AND is_main = TRUE;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_check_single_main_sucursal ON public.sucursales;
CREATE TRIGGER trigger_check_single_main_sucursal
    BEFORE INSERT OR UPDATE ON public.sucursales
    FOR EACH ROW
    WHEN (NEW.is_main = TRUE)
    EXECUTE FUNCTION check_single_main_sucursal();

-- Enable RLS
ALTER TABLE public.sucursales ENABLE ROW LEVEL SECURITY;

-- Comment on table
COMMENT ON TABLE public.sucursales IS 'Tabla de sucursales/branches de cada negocio en el sistema multi-tenant';
COMMENT ON COLUMN public.sucursales.is_main IS 'Indica si es la sucursal principal del negocio';
COMMENT ON COLUMN public.sucursales.dias_operacion IS 'Array JSON con los días de operación de la sucursal';