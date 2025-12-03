-- Add unidades column to productos table
ALTER TABLE public.productos ADD COLUMN IF NOT EXISTS unidades VARCHAR(50);
