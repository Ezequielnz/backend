-- Create a function to handle new user creation
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
DECLARE
  new_negocio_id uuid;
  user_nombre text;
  user_apellido text;
  user_rol text;
BEGIN
  -- Extract metadata
  user_nombre := new.raw_user_meta_data->>'nombre';
  user_apellido := new.raw_user_meta_data->>'apellido';
  user_rol := COALESCE(new.raw_user_meta_data->>'rol', 'usuario');

  -- 1. Insert into public.usuarios
  INSERT INTO public.usuarios (id, email, nombre, apellido, rol, creado_en, ultimo_acceso)
  VALUES (
    new.id,
    new.email,
    user_nombre,
    user_apellido,
    user_rol,
    now(),
    now()
  );

  -- 2. If role is owner (self-registration), create a new business
  IF user_rol = 'owner' OR user_rol = 'dueno' THEN
      INSERT INTO public.negocios (nombre, creada_por)
      VALUES (
        'Negocio de ' || COALESCE(user_nombre, 'Usuario'),
        new.id
      )
      RETURNING id INTO new_negocio_id;

      -- 3. Link user to business as admin
      INSERT INTO public.usuarios_negocios (usuario_id, negocio_id, rol, estado)
      VALUES (
        new.id,
        new_negocio_id,
        'admin',
        'aceptado'
      );
  END IF;

  RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create the trigger
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();
