from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
import jwt

from app.db.supabase_client import get_supabase_user_client
from app.dependencies import PermissionDependency
from app.schemas.tenant_settings import TenantSettingsCreate, TenantSettingsUpdate, TenantSettings


def _get_user_id_from_token(authorization: str) -> str:
    """Extract user ID from JWT token"""
    try:
        token = authorization or ""
        if token.startswith("Bearer "):
            token = token[7:]
        decoded = jwt.decode(token, options={"verify_signature": False})
        user_id = decoded.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token JWT inválido: no contiene user_id")
        return user_id
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Error al procesar token: {str(e)}")


async def _verify_admin_or_owner_access(business_id: str, authorization: str) -> bool:
    """Verify if user is admin or owner of the business"""
    user_id = _get_user_id_from_token(authorization)
    client = get_supabase_user_client(authorization)
    
    # Check if user is the business creator
    business_resp = client.table("negocios").select("creada_por").eq("id", business_id).execute()
    if business_resp.data and business_resp.data[0].get("creada_por") == user_id:
        return True
    
    # Check if user is admin of the business
    admin_resp = client.table("usuarios_negocios").select("rol").eq("usuario_id", user_id).eq("negocio_id", business_id).eq("estado", "aceptado").execute()
    if admin_resp.data and admin_resp.data[0].get("rol") == "admin":
        return True
    
    # Check if user has acceso_total
    permisos_resp = client.table("usuarios_negocios").select("id").eq("usuario_id", user_id).eq("negocio_id", business_id).eq("estado", "aceptado").execute()
    if permisos_resp.data:
        usuario_negocio_id = permisos_resp.data[0]["id"]
        access_resp = client.table("permisos_usuario_negocio").select("acceso_total").eq("usuario_negocio_id", usuario_negocio_id).execute()
        if access_resp.data and access_resp.data[0].get("acceso_total"):
            return True
    
    return False

router = APIRouter()


@router.get("/")
async def get_tenant_settings(
    business_id: str,
    request: Request,
) -> Any:
    """
    Obtiene la configuración del tenant para un negocio.
    Permite acceso a admins, owners y usuarios con permisos de facturación.
    """
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=401, detail="Token de autorización requerido")
    
    # Check if user is admin/owner or has facturacion permissions
    try:
        is_admin_or_owner = await _verify_admin_or_owner_access(business_id, authorization)
        if not is_admin_or_owner:
            # If not admin/owner, check facturacion permissions
            permission_dep = PermissionDependency("facturacion", "ver")
            await permission_dep(business_id=business_id, request=request)
    except HTTPException:
        raise HTTPException(status_code=403, detail="No tienes permisos para ver la configuración del negocio")

    client = get_supabase_user_client(authorization)

    try:
        # Buscar configuración existente para este negocio
        response = client.table("tenant_settings").select("*").eq("tenant_id", business_id).execute()
        
        if response.data and len(response.data) > 0:
            return JSONResponse(content=response.data[0])
        else:
            # Si no existe configuración, devolver valores por defecto
            default_settings = {
                "locale": "es-AR",
                "timezone": "America/Argentina/Buenos_Aires", 
                "currency": "ARS",
                "sales_drop_threshold": 15,
                "min_days_for_model": 30
            }
            return JSONResponse(content=default_settings)
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener configuración: {str(e)}")


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED
)
async def create_or_update_tenant_settings(
    business_id: str,
    settings_data: TenantSettingsCreate,
    request: Request,
) -> Any:
    """
    Crea o actualiza la configuración del tenant para un negocio.
    Solo admins, owners y usuarios con permisos de facturación pueden editar.
    """
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=401, detail="Token de autorización requerido")
    
    # Check if user is admin/owner or has facturacion edit permissions
    try:
        is_admin_or_owner = await _verify_admin_or_owner_access(business_id, authorization)
        if not is_admin_or_owner:
            # If not admin/owner, check facturacion permissions
            permission_dep = PermissionDependency("facturacion", "editar")
            await permission_dep(business_id=business_id, request=request)
    except HTTPException:
        raise HTTPException(status_code=403, detail="No tienes permisos para editar la configuración del negocio")

    client = get_supabase_user_client(authorization)

    try:
        # Verificar si ya existe configuración para este negocio
        existing_response = client.table("tenant_settings").select("*").eq("tenant_id", business_id).execute()
        
        # Preparar datos para insertar/actualizar
        settings_dict = settings_data.model_dump(exclude_unset=True)
        settings_dict["tenant_id"] = business_id
        
        if existing_response.data and len(existing_response.data) > 0:
            # Actualizar configuración existente
            response = client.table("tenant_settings").update(settings_dict).eq("tenant_id", business_id).execute()
        else:
            # Crear nueva configuración
            response = client.table("tenant_settings").insert(settings_dict).execute()
        
        if not response.data:
            raise HTTPException(status_code=500, detail="Error al guardar la configuración")
            
        return JSONResponse(content=response.data[0])
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar configuración: {str(e)}")


@router.put("/{tenant_id}")
async def update_tenant_settings(
    business_id: str,
    tenant_id: str,
    settings_data: TenantSettingsUpdate,
    request: Request,
) -> Any:
    """
    Actualiza la configuración del tenant para un negocio específico.
    Solo admins, owners y usuarios con permisos de facturación pueden editar.
    """
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=401, detail="Token de autorización requerido")
    
    # Check if user is admin/owner or has facturacion edit permissions
    try:
        is_admin_or_owner = await _verify_admin_or_owner_access(business_id, authorization)
        if not is_admin_or_owner:
            # If not admin/owner, check facturacion permissions
            permission_dep = PermissionDependency("facturacion", "editar")
            await permission_dep(business_id=business_id, request=request)
    except HTTPException:
        raise HTTPException(status_code=403, detail="No tienes permisos para editar la configuración del negocio")

    client = get_supabase_user_client(authorization)

    try:
        # Preparar datos para actualizar
        settings_dict = settings_data.model_dump(exclude_unset=True)
        
        # Actualizar configuración
        response = client.table("tenant_settings").update(settings_dict).eq("tenant_id", business_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Configuración no encontrada")
            
        return JSONResponse(content=response.data[0])
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al actualizar configuración: {str(e)}")


@router.delete("/{tenant_id}")
async def delete_tenant_settings(
    business_id: str,
    tenant_id: str,
    request: Request,
) -> Any:
    """
    Elimina la configuración del tenant para un negocio.
    Solo admins, owners y usuarios con permisos de facturación pueden eliminar.
    """
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=401, detail="Token de autorización requerido")
    
    # Check if user is admin/owner or has facturacion edit permissions
    try:
        is_admin_or_owner = await _verify_admin_or_owner_access(business_id, authorization)
        if not is_admin_or_owner:
            # If not admin/owner, check facturacion permissions
            permission_dep = PermissionDependency("facturacion", "editar")
            await permission_dep(business_id=business_id, request=request)
    except HTTPException:
        raise HTTPException(status_code=403, detail="No tienes permisos para eliminar la configuración del negocio")

    client = get_supabase_user_client(authorization)

    try:
        response = client.table("tenant_settings").delete().eq("tenant_id", business_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Configuración no encontrada")
            
        return JSONResponse(content={"message": "Configuración eliminada correctamente"})
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar configuración: {str(e)}")
