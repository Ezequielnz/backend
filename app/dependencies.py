from fastapi import Depends, HTTPException, status, Request
from app.db.supabase_client import get_supabase_client
from typing import Optional, List

async def verify_task_view_permission(request: Request, negocio_id: str) -> bool:
    """Dependency to verify if the user has 'puede_ver_tareas' permission for a business."""
    user = request.state.user
    if not user:
        # This should ideally not happen if auth_middleware is used before this dependency
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated.",
        )

    supabase = get_supabase_client()

    # 1. Get user's relationship and id for the business
    # We select 'id' from usuarios_negocios to link to permisos_usuario_negocio
    user_business_response = supabase.table("usuarios_negocios").select("id").eq("usuario_id", user.id).eq("negocio_id", negocio_id).execute()

    if not user_business_response.data or len(user_business_response.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with this business or invalid negocio_id.",
        )

    usuario_negocio_id = user_business_response.data[0].get("id")

    # 2. Check fine-grained permission 'puede_ver_tareas'
    permissions_response = supabase.table("permisos_usuario_negocio").select("puede_ver_tareas").eq("usuario_negocio_id", usuario_negocio_id).execute()

    # Check if data exists and 'puede_ver_tareas' is True
    if not permissions_response.data or len(permissions_response.data) == 0 or not permissions_response.data[0].get("puede_ver_tareas", False):
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view tasks for this business.",
        )

    # If all checks pass
    return True

async def verify_permission_logic(request: Request, business_id: str, required_permission: str):
    """Core logic to verify if the user has a specific permission for a business."""
    user = request.state.user
    if not user:
         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated")
    
    supabase = get_supabase_client()

    user_business_response = supabase.table("usuarios_negocios").select("id", "rol").eq("usuario_id", user.id).eq("negocio_id", business_id).execute()
    
    if not user_business_response.data or len(user_business_response.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with this business or invalid business_id.",
        )

    user_business_info = user_business_response.data[0]
    usuario_negocio_id = user_business_info.get("id")

    # Admins have all permissions
    if user_business_info.get("rol") == "admin":
        return True

    permissions_response = supabase.table("permisos_usuario_negocio").select(required_permission).eq("usuario_negocio_id", usuario_negocio_id).execute()

    if not permissions_response.data or len(permissions_response.data) == 0 or not permissions_response.data[0].get(required_permission, False):
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not have permission: {required_permission}",
        )

    return True

# Re-export verify_permission_logic as verify_permission for backward compatibility
verify_permission = verify_permission_logic

# New dependency class to inject required permission
class PermissionDependency:
    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    async def __call__(self, request: Request, business_id: str):
        # The business_id is automatically injected by FastAPI from the path parameter
        await verify_permission_logic(request, business_id, self.required_permission)
        return True # Dependency must return something on success

# Remove the old verify_permission function
# async def verify_permission(request: Request, business_id: str, required_permission: str):
#    ...

# Keep verify_task_view_permission for now if it's still used elsewhere, 
# but ideally, it should also use the new PermissionDependency.
# async def verify_task_view_permission(request: Request, negocio_id: str) -> bool:
#   ... 