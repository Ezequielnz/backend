-- Script para corregir la recursión infinita en las políticas RLS de usuarios_negocios
-- El problema surge porque las políticas de INSERT consultan la misma tabla que están protegiendo

-- Eliminar las políticas problemáticas
DROP POLICY IF EXISTS "usuarios_negocios_invite_only_policy" ON usuarios_negocios;
DROP POLICY IF EXISTS "usuarios_negocios_admin_update_policy" ON usuarios_negocios;

-- Crear función auxiliar para verificar si un usuario es creador de un negocio
-- sin usar RLS (usando SECURITY DEFINER)
CREATE OR REPLACE FUNCTION es_creador_negocio(usuario_id uuid, negocio_id uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    -- Verificar directamente sin RLS si el usuario creó el negocio
    RETURN EXISTS (
        SELECT 1 
        FROM negocios 
        WHERE id = negocio_id 
        AND creada_por = usuario_id
    );
END;
$$;

-- Crear función auxiliar para verificar si un usuario es admin de un negocio
-- sin usar RLS (usando SECURITY DEFINER) 
CREATE OR REPLACE FUNCTION es_admin_negocio(usuario_id uuid, negocio_id uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    -- Verificar directamente sin RLS si el usuario es admin del negocio
    RETURN EXISTS (
        SELECT 1 
        FROM usuarios_negocios 
        WHERE usuario_id = usuario_id 
        AND negocio_id = negocio_id
        AND rol = 'admin' 
        AND estado = 'aceptado'
    );
END;
$$;

-- Nueva política de INSERT que usa las funciones auxiliares para evitar recursión
CREATE POLICY "usuarios_negocios_insert_policy" ON usuarios_negocios
FOR INSERT 
WITH CHECK (
    -- Solo el creador del negocio puede insertar usuarios
    es_creador_negocio(auth.uid(), negocio_id)
    OR
    -- O usuarios que son admins del negocio pueden insertar
    es_admin_negocio(auth.uid(), negocio_id)
);

-- Nueva política de UPDATE que usa las funciones auxiliares 
CREATE POLICY "usuarios_negocios_update_policy" ON usuarios_negocios
FOR UPDATE 
USING (
    -- Solo el creador del negocio puede actualizar
    es_creador_negocio(auth.uid(), negocio_id)
    OR
    -- O usuarios que son admins del negocio pueden actualizar
    es_admin_negocio(auth.uid(), negocio_id)
    OR
    -- O el propio usuario puede actualizar su estado (aceptar/rechazar)
    usuario_id = auth.uid()
)
WITH CHECK (
    -- Mismas condiciones para WITH CHECK
    es_creador_negocio(auth.uid(), negocio_id)
    OR
    es_admin_negocio(auth.uid(), negocio_id)
    OR
    usuario_id = auth.uid()
);

-- Otorgar permisos de ejecución a las funciones
GRANT EXECUTE ON FUNCTION es_creador_negocio(uuid, uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION es_admin_negocio(uuid, uuid) TO authenticated;

-- Comentarios para documentación
COMMENT ON FUNCTION es_creador_negocio(uuid, uuid) IS 'Verifica si un usuario es el creador de un negocio sin usar RLS para evitar recursión';
COMMENT ON FUNCTION es_admin_negocio(uuid, uuid) IS 'Verifica si un usuario es admin de un negocio sin usar RLS para evitar recursión'; 