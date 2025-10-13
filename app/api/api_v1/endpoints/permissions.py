from fastapi import APIRouter, Depends, HTTPException, status, Request
from app.db.supabase_client import get_supabase_user_client, get_supabase_anon_client
from app.api.deps import get_current_user_from_request as get_current_user
from typing import Dict, Any
from pydantic import BaseModel

router = APIRouter()

class UserPermissionsResponse(BaseModel):
    user_id: str
    business_id: str
    role: str
    is_creator: bool
    is_admin: bool
    has_full_access: bool
    permissions: Dict[str, bool]

@router.get("/businesses/{business_id}/permissions", response_model=UserPermissionsResponse)
async def get_user_permissions(
    request: Request,
    business_id: str,
    current_user = Depends(get_current_user)
):
    """
    Get all user permissions for a specific business.
    Returns comprehensive permission object for frontend caching.
    """
    try:
        token = request.headers.get("Authorization", "")
        supabase = get_supabase_user_client(token) if token else get_supabase_anon_client()
        
        # Verificar acceso al negocio
        user_business_response = supabase.table("usuarios_negocios") \
            .select("id, rol") \
            .eq("usuario_id", current_user.id) \
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
        role = user_business_info.get("rol")

        # Verificar si es el creador del negocio
        business_response = supabase.table("negocios").select("creada_por").eq("id", business_id).execute()
        is_creator = bool(
            business_response.data and 
            len(business_response.data) > 0 and 
            business_response.data[0].get("creada_por") == current_user.id
        )
        
        # Los admins y creadores tienen todos los permisos
        is_admin = bool(role == "admin")
        has_full_access = bool(is_creator or is_admin)
        
        # Definir todos los permisos disponibles
        all_permissions = {
            "puede_ver_productos": True,
            "puede_editar_productos": True,
            "puede_eliminar_productos": True,
            "puede_ver_clientes": True,
            "puede_editar_clientes": True,
            "puede_eliminar_clientes": True,
            "puede_ver_categorias": True,
            "puede_editar_categorias": True,
            "puede_eliminar_categorias": True,
            "puede_ver_ventas": True,
            "puede_editar_ventas": True,
            "puede_ver_stock": True,
            "puede_editar_stock": True,
            "puede_ver_facturacion": True,
            "puede_editar_facturacion": True,
            "puede_ver_tareas": True,
            "puede_asignar_tareas": True,
            "puede_editar_tareas": True,
            "puede_ver_configuracion": True,
            "puede_editar_configuracion": True
        }
        
        if has_full_access:
            # Creadores y admins tienen todos los permisos
            permissions = all_permissions
        else:
            # Para usuarios regulares, consultar permisos específicos
            permissions_response = supabase.table("permisos_usuario_negocio") \
                .select("*") \
                .eq("usuario_negocio_id", usuario_negocio_id) \
                .execute()
            
            if not permissions_response.data:
                # Si no hay permisos configurados, denegar todos
                permissions = {key: False for key in all_permissions.keys()}
            else:
                permisos = permissions_response.data[0]
                
                # Si tiene acceso total, otorgar todos los permisos
                if permisos.get("acceso_total", False):
                    permissions = all_permissions
                else:
                    # Mapear permisos específicos
                    permissions = {
                        key: bool(permisos.get(key, False)) 
                        for key in all_permissions.keys()
                    }

        return UserPermissionsResponse(
            user_id=current_user.id,
            business_id=business_id,
            role=role,
            is_creator=is_creator,
            is_admin=is_admin,
            has_full_access=has_full_access,
            permissions=permissions
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error inesperado en get_user_permissions: {type(e).__name__} - {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al obtener permisos"
        ) 