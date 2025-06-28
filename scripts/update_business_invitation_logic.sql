-- Script para actualizar las políticas RLS según la nueva lógica de invitaciones
-- Solo los administradores de negocio pueden invitar usuarios, no al revés

-- Eliminar la política actual de INSERT que permite a usuarios solicitar unirse
DROP POLICY IF EXISTS "usuarios_negocios_insert_policy" ON usuarios_negocios;

-- Crear nueva política de INSERT que solo permite:
-- 1. Al creador del negocio invitar usuarios (cuando es admin)
-- 2. A usuarios con rol admin en el negocio invitar otros usuarios
CREATE POLICY "usuarios_negocios_invite_only_policy" ON usuarios_negocios
FOR INSERT 
WITH CHECK (
  -- Solo el creador del negocio puede invitar usuarios
  negocio_id IN (
    SELECT n.id 
    FROM negocios n 
    WHERE n.creada_por = auth.uid()
  )
  OR
  -- O usuarios con rol admin en ese negocio pueden invitar
  negocio_id IN (
    SELECT un.negocio_id 
    FROM usuarios_negocios un 
    WHERE un.usuario_id = auth.uid() 
    AND un.rol = 'admin' 
    AND un.estado = 'aceptado'
  )
);

-- Actualizar política de UPDATE para que solo admins puedan cambiar estados
DROP POLICY IF EXISTS "usuarios_negocios_update_policy" ON usuarios_negocios;

CREATE POLICY "usuarios_negocios_admin_update_policy" ON usuarios_negocios
FOR UPDATE 
USING (
  -- Solo el creador del negocio puede actualizar
  negocio_id IN (
    SELECT n.id 
    FROM negocios n 
    WHERE n.creada_por = auth.uid()
  )
  OR
  -- O usuarios con rol admin en ese negocio pueden actualizar
  negocio_id IN (
    SELECT un.negocio_id 
    FROM usuarios_negocios un 
    WHERE un.usuario_id = auth.uid() 
    AND un.rol = 'admin' 
    AND un.estado = 'aceptado'
  )
)
WITH CHECK (
  -- Misma lógica para el WITH CHECK
  negocio_id IN (
    SELECT n.id 
    FROM negocios n 
    WHERE n.creada_por = auth.uid()
  )
  OR
  negocio_id IN (
    SELECT un.negocio_id 
    FROM usuarios_negocios un 
    WHERE un.usuario_id = auth.uid() 
    AND un.rol = 'admin' 
    AND un.estado = 'aceptado'
  )
);

-- Comentarios sobre los cambios:
-- 1. Ahora solo los administradores pueden invitar usuarios a negocios
-- 2. Los usuarios ya no pueden solicitar unirse a negocios existentes al registrarse
-- 3. Cada nuevo usuario registrado automáticamente crea su propio negocio como admin
-- 4. En el futuro, se implementará un sistema de invitaciones por email 