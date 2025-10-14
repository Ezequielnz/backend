-- Patch: Make update_updated_at_column() robust to tables without updated_at
-- This redefines the trigger function to attempt updated_at, then actualizado_en, else no-op
-- Safe to run multiple times (CREATE OR REPLACE FUNCTION)

CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS trigger AS $$
BEGIN
  -- Try standard updated_at column
  BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
  EXCEPTION WHEN undefined_column THEN
    -- Fallback to actualizado_en (spanish naming)
    BEGIN
      NEW.actualizado_en = NOW();
      RETURN NEW;
    EXCEPTION WHEN undefined_column THEN
      -- Neither column exists: do nothing
      RETURN NEW;
    END;
  END;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
  RAISE NOTICE 'update_updated_at_column() patched to be column-aware (updated_at/actualizado_en or no-op).';
END $$;