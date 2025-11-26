-- Fix public.usuarios table definition
-- This script ensures the table exists and has the correct schema to work with the trigger.

-- 1. Create table if not exists (or recreate if needed - careful with data loss!)
-- Since we are debugging a registration error, we assume we can fix the schema.
-- If the table exists with 'id serial', it needs to be changed.

CREATE TABLE IF NOT EXISTS public.usuarios (
    id UUID REFERENCES auth.users ON DELETE CASCADE NOT NULL PRIMARY KEY,
    email TEXT UNIQUE,
    nombre TEXT,
    apellido TEXT,
    rol TEXT DEFAULT 'usuario',
    creado_en TIMESTAMPTZ DEFAULT now(),
    ultimo_acceso TIMESTAMPTZ,
    permisos TEXT[] DEFAULT '{}'::TEXT[]
);

-- 2. Grant permissions
GRANT ALL ON public.usuarios TO postgres;
GRANT ALL ON public.usuarios TO anon;
GRANT ALL ON public.usuarios TO authenticated;
GRANT ALL ON public.usuarios TO service_role;

-- 3. Enable RLS
ALTER TABLE public.usuarios ENABLE ROW LEVEL SECURITY;

-- 4. Policies
DROP POLICY IF EXISTS "Users can view own profile" ON public.usuarios;
CREATE POLICY "Users can view own profile" ON public.usuarios
    FOR SELECT USING (auth.uid() = id);

DROP POLICY IF EXISTS "Users can update own profile" ON public.usuarios;
CREATE POLICY "Users can update own profile" ON public.usuarios
    FOR UPDATE USING (auth.uid() = id);

-- 5. Re-apply trigger just in case
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();
