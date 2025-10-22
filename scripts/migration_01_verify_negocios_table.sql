-- =====================================================
-- Migration 01: Verify and Update NEGOCIOS Table
-- =====================================================
-- Description: Ensures the negocios table exists with all required fields
-- Author: Database Migration Script
-- Date: 2025-01-20
-- =====================================================

-- Check if negocios table exists, if not create it
CREATE TABLE IF NOT EXISTS public.negocios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre VARCHAR(255) NOT NULL,
    cuit VARCHAR(20) UNIQUE,
    razon_social VARCHAR(255),
    direccion TEXT,
    telefono VARCHAR(50),
    email VARCHAR(255),
    logo_url TEXT,
    rubro VARCHAR(100),
    plan_id UUID,
    estado VARCHAR(50) DEFAULT 'activo' CHECK (estado IN ('activo', 'suspendido', 'inactivo')),
    fecha_alta TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    fecha_vencimiento TIMESTAMP WITH TIME ZONE,
    configuracion JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Add missing columns if they don't exist
DO $$ 
BEGIN
    -- Add cuit if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'negocios' 
                   AND column_name = 'cuit') THEN
        ALTER TABLE public.negocios ADD COLUMN cuit VARCHAR(20) UNIQUE;
    END IF;

    -- Add razon_social if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'negocios' 
                   AND column_name = 'razon_social') THEN
        ALTER TABLE public.negocios ADD COLUMN razon_social VARCHAR(255);
    END IF;

    -- Add direccion if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'negocios' 
                   AND column_name = 'direccion') THEN
        ALTER TABLE public.negocios ADD COLUMN direccion TEXT;
    END IF;

    -- Add telefono if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'negocios' 
                   AND column_name = 'telefono') THEN
        ALTER TABLE public.negocios ADD COLUMN telefono VARCHAR(50);
    END IF;

    -- Add email if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'negocios' 
                   AND column_name = 'email') THEN
        ALTER TABLE public.negocios ADD COLUMN email VARCHAR(255);
    END IF;

    -- Add logo_url if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'negocios' 
                   AND column_name = 'logo_url') THEN
        ALTER TABLE public.negocios ADD COLUMN logo_url TEXT;
    END IF;

    -- Add rubro if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'negocios' 
                   AND column_name = 'rubro') THEN
        ALTER TABLE public.negocios ADD COLUMN rubro VARCHAR(100);
    END IF;

    -- Add plan_id if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'negocios' 
                   AND column_name = 'plan_id') THEN
        ALTER TABLE public.negocios ADD COLUMN plan_id UUID;
    END IF;

    -- Add estado if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'negocios' 
                   AND column_name = 'estado') THEN
        ALTER TABLE public.negocios ADD COLUMN estado VARCHAR(50) DEFAULT 'activo';
        ALTER TABLE public.negocios ADD CONSTRAINT negocios_estado_check 
            CHECK (estado IN ('activo', 'suspendido', 'inactivo'));
    END IF;

    -- Add fecha_alta if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'negocios' 
                   AND column_name = 'fecha_alta') THEN
        ALTER TABLE public.negocios ADD COLUMN fecha_alta TIMESTAMP WITH TIME ZONE DEFAULT NOW();
    END IF;

    -- Add fecha_vencimiento if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'negocios' 
                   AND column_name = 'fecha_vencimiento') THEN
        ALTER TABLE public.negocios ADD COLUMN fecha_vencimiento TIMESTAMP WITH TIME ZONE;
    END IF;

    -- Add configuracion if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'negocios' 
                   AND column_name = 'configuracion') THEN
        ALTER TABLE public.negocios ADD COLUMN configuracion JSONB DEFAULT '{}';
    END IF;

    -- Add created_at if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'negocios' 
                   AND column_name = 'created_at') THEN
        ALTER TABLE public.negocios ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
    END IF;

    -- Add updated_at if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'negocios' 
                   AND column_name = 'updated_at') THEN
        ALTER TABLE public.negocios ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
    END IF;
END $$;

-- Create index on plan_id for performance
CREATE INDEX IF NOT EXISTS idx_negocios_plan_id ON public.negocios(plan_id);

-- Create index on estado for filtering
CREATE INDEX IF NOT EXISTS idx_negocios_estado ON public.negocios(estado);

-- Create index on cuit for lookups
CREATE INDEX IF NOT EXISTS idx_negocios_cuit ON public.negocios(cuit);

-- Add foreign key to planes if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_negocios_plan_id' 
        AND table_name = 'negocios'
    ) THEN
        ALTER TABLE public.negocios 
        ADD CONSTRAINT fk_negocios_plan_id 
        FOREIGN KEY (plan_id) REFERENCES public.planes(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Create or replace trigger for updated_at
CREATE OR REPLACE FUNCTION update_negocios_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_negocios_updated_at ON public.negocios;
CREATE TRIGGER trigger_negocios_updated_at
    BEFORE UPDATE ON public.negocios
    FOR EACH ROW
    EXECUTE FUNCTION update_negocios_updated_at();

-- Enable RLS
ALTER TABLE public.negocios ENABLE ROW LEVEL SECURITY;

-- Comment on table
COMMENT ON TABLE public.negocios IS 'Tabla principal que representa cada empresa/negocio en el sistema multi-tenant';