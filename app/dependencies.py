from fastapi import Depends, HTTPException, status, Request
from app.db.supabase_client import get_supabase_client, get_supabase_user_client
from typing import Optional, List

def is_public_products_services_request(request: Request) -> bool:
    """Detecta si la request corresponde a rutas públicas temporales de productos/servicios.
    Se considera pública SOLO para consultas GET (listado/detalle) y cuando no hay usuario adjunto.
    """
    path = request.url.path if hasattr(request, "url") else ""
    return (
        request.method == "GET"
        and "/businesses/" in path
        and ("/products" in path or "/services" in path)
    )

async def verify_task_view_permission(request: Request, negocio_id: str) -> bool:
    """Dependency to verify if the user has 'puede_ver_tareas' permission for a business."""
    return await verify_permission_logic(request, negocio_id, "puede_ver_tareas")

async def verify_permission_logic(request: Request, business_id: str, required_permission: str):
    """Core logic to verify if the user has a specific permission for a business."""
    try:
        user = getattr(request.state, 'user', None)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated")
        
        authorization = request.headers.get("Authorization", "")
        if not authorization:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
        
        user_id = getattr(user, "id", None)
        if user_id is None and isinstance(user, dict):
            user_id = user.get("id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User id not available")
        
        supabase = get_supabase_user_client(authorization)

        # Verificar acceso al negocio
        user_business_response = supabase.table("usuarios_negocios") \
            .select("id, rol") \
            .eq("usuario_id", user_id) \
            .eq("negocio_id", business_id) \
            .eq("estado", "aceptado") \
            .execute()
        
        if not user_business_response.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a este negocio o tu acceso está pendiente de aprobación.",
            )

        user_business_info = user_business_response.data[0]
        usuario_negocio_id = user_business_info.get("id")

        # Verificar si es el creador del negocio
        business_response = supabase.table("negocios").select("creada_por").eq("id", business_id).execute()
        if business_response.data and business_response.data[0].get("creada_por") == user_id:
            return True

        # Los admins tienen todos los permisos
        if user_business_info.get("rol") == "admin":
            return True

        # Verificar permisos específicos
        permissions_response = supabase.table("permisos_usuario_negocio") \
            .select("acceso_total, " + required_permission) \
            .eq("usuario_negocio_id", usuario_negocio_id) \
            .execute()

        if not permissions_response.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos configurados para este negocio. Contacta al administrador.",
            )

        permisos = permissions_response.data[0]
        
        # Verificar acceso total
        if permisos.get("acceso_total", False):
            return True
        
        # Verificar permiso específico
        if not permisos.get(required_permission, False):
            # Mapear nombres de permisos a mensajes amigables
            permission_messages = {
                "puede_ver_productos": "ver productos",
                "puede_editar_productos": "editar productos", 
                "puede_eliminar_productos": "eliminar productos",
                "puede_ver_clientes": "ver clientes",
                "puede_editar_clientes": "editar clientes",
                "puede_eliminar_clientes": "eliminar clientes",
                "puede_ver_categorias": "ver categorías",
                "puede_editar_categorias": "editar categorías",
                "puede_eliminar_categorias": "eliminar categorías",
                "puede_ver_ventas": "ver ventas",
                "puede_editar_ventas": "editar ventas",
                "puede_ver_stock": "ver inventario",
                "puede_editar_stock": "editar inventario",
                "puede_ver_facturacion": "ver facturación",
                "puede_editar_facturacion": "editar facturación",
                "puede_ver_tareas": "ver tareas",
                "puede_asignar_tareas": "asignar tareas",
                "puede_editar_tareas": "editar tareas",
                "puede_ver_configuracion": "ver configuración",
                "puede_editar_configuracion": "editar configuración"
            }
            
            message = permission_messages.get(required_permission, f"usar {required_permission}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No tienes permisos para {message}. Contacta al administrador para solicitar acceso.",
            )

        return True
        
    except HTTPException:
        # Re-raise HTTPExceptions as they are expected
        raise
    except Exception as e:
        # Log unexpected errors and convert to 500
        print(f"❌ Error inesperado en verify_permission_logic: {type(e).__name__} - {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al verificar permisos"
        )

async def verify_resource_permission_logic(request: Request, business_id: str, recurso: str, accion: str):
    """Core logic to verify if the user has a specific resource/action permission for a business."""
    try:
        # Mapear recurso/accion al nuevo sistema de permisos
        permission_mapping = {
            ("productos", "ver"): "puede_ver_productos",
            ("productos", "editar"): "puede_editar_productos",
            ("productos", "eliminar"): "puede_eliminar_productos",
            ("clientes", "ver"): "puede_ver_clientes",
            ("clientes", "editar"): "puede_editar_clientes",
            ("clientes", "eliminar"): "puede_eliminar_clientes",
            ("categorias", "ver"): "puede_ver_categorias",
            ("categorias", "editar"): "puede_editar_categorias",
            ("categorias", "eliminar"): "puede_eliminar_categorias",
            ("ventas", "ver"): "puede_ver_ventas",
            ("ventas", "editar"): "puede_editar_ventas",
            ("stock", "ver"): "puede_ver_stock",
            ("stock", "editar"): "puede_editar_stock",
            ("facturacion", "ver"): "puede_ver_facturacion",
            ("facturacion", "editar"): "puede_editar_facturacion",
            ("tareas", "ver"): "puede_ver_tareas",
            ("tareas", "asignar"): "puede_asignar_tareas",
            ("tareas", "editar"): "puede_editar_tareas",
            # Configuración/Notificaciones (para configurar reglas y preferencias)
            ("configuracion", "ver"): "puede_ver_configuracion",
            ("configuracion", "editar"): "puede_editar_configuracion",
            # Alias opcional por si alguna ruta usa "notifications"
            ("notifications", "ver"): "puede_ver_configuracion",
            ("notifications", "editar"): "puede_editar_configuracion"
        }
        
        permission_name = permission_mapping.get((recurso, accion))
        if not permission_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Permiso no reconocido: {recurso}/{accion}"
            )
        
        return await verify_permission_logic(request, business_id, permission_name)
        
    except HTTPException:
        # Re-raise HTTPExceptions as they are expected
        raise
    except Exception as e:
        # Log unexpected errors and convert to 500
        print(f"❌ Error inesperado en verify_resource_permission_logic: {type(e).__name__} - {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al verificar permisos de recurso"
        )

# Re-export verify_permission_logic as verify_permission for backward compatibility
verify_permission = verify_permission_logic

# Legacy dependency class to inject required permission
class LegacyPermissionDependency:
    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    async def __call__(self, request: Request, business_id: str):
        try:
            # Permitir acceso público temporal para GET de productos/servicios sin usuario autenticado
            if is_public_products_services_request(request) and getattr(request.state, "user", None) is None:
                return True
            # The business_id is automatically injected by FastAPI from the path parameter
            await verify_permission_logic(request, business_id, self.required_permission)
            return True # Dependency must return something on success
        except HTTPException:
            # Re-raise HTTPExceptions as they are expected
            raise
        except Exception as e:
            # Log unexpected errors and convert to 500
            print(f"❌ Error inesperado en LegacyPermissionDependency: {type(e).__name__} - {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error interno del servidor en verificación de permisos"
            )

# New dependency class for resource/action permissions
class ResourcePermissionDependency:
    def __init__(self, recurso: str, accion: str):
        self.recurso = recurso
        self.accion = accion

    async def __call__(self, request: Request, business_id: str):
        try:
            # Permitir acceso público temporal para GET de productos/servicios sin usuario autenticado
            if is_public_products_services_request(request) and getattr(request.state, "user", None) is None:
                return True
            # The business_id is automatically injected by FastAPI from the path parameter
            await verify_resource_permission_logic(request, business_id, self.recurso, self.accion)
            return True # Dependency must return something on success
        except HTTPException:
            # Re-raise HTTPExceptions as they are expected
            raise
        except Exception as e:
            # Log unexpected errors and convert to 500
            print(f"❌ Error inesperado en ResourcePermissionDependency: {type(e).__name__} - {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error interno del servidor en verificación de permisos de recurso"
            )

# Convenience function to create resource permission dependencies
def PermissionDependency(recurso: str, accion: Optional[str] = None):
    """
    Create a permission dependency. 
    If accion is provided, uses the new resource/action pattern.
    If accion is None, uses the legacy permission name pattern.
    """
    if accion is not None:
        return ResourcePermissionDependency(recurso, accion)
    else:
        # Legacy mode - recurso is actually the permission name
        return LegacyPermissionDependency(recurso)

# Remove the old verify_permission function
# async def verify_permission(request: Request, business_id: str, required_permission: str):
#    ...

# Keep verify_task_view_permission for now if it's still used elsewhere, 
# but ideally, it should also use the new PermissionDependency.
# async def verify_task_view_permission(request: Request, negocio_id: str) -> bool:
#   ... 