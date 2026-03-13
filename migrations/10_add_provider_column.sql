-- Add proveedor_id column to productos table
ALTER TABLE public.productos ADD COLUMN IF NOT EXISTS proveedor_id UUID REFERENCES public.proveedores(id);
