from typing import Dict, Any, Optional, TypedDict
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from app.db.supabase_client import get_supabase_client
from app.db.session import get_db
from app.types.auth import User
import jwt

class UserData(TypedDict):
    id: str
    email: Optional[str]
    rol: str
    activo: bool

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserData:
    """
    Get the current authenticated user from the token.
    
    Args:
        token: JWT token from OAuth2 scheme
        
    Returns:
        UserData: User information including id, email, role and active status
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    supabase = get_supabase_client()
    
    try:
        auth_response = supabase.auth.get_user(token)
        
        if not auth_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user_id = auth_response.user.id
        user_response = supabase.table("usuarios").select("*").eq("id", user_id).execute()
        
        if not user_response.data:
            return {
                "id": user_id,
                "email": auth_response.user.email,
                "rol": "usuario",
                "activo": True
            }
            
        return user_response.data[0]
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_active_user(
    current_user: UserData = Depends(get_current_user)
) -> UserData:
    """
    Check if the current user is active.
    
    Args:
        current_user: User data from get_current_user dependency
        
    Returns:
        UserData: User information if active
        
    Raises:
        HTTPException: If user is inactive
    """
    if not current_user.get("activo", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user

async def get_admin_user(
    current_user: UserData = Depends(get_current_active_user)
) -> UserData:
    """
    Check if the current user is an admin.
    
    Args:
        current_user: User data from get_current_active_user dependency
        
    Returns:
        UserData: User information if admin
        
    Raises:
        HTTPException: If user is not admin
    """
    if current_user.get("rol") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user

async def verify_user_access(user_id: str) -> bool:
    """Verificar que el usuario tiene email confirmado y está aprobado en al menos un negocio."""
    supabase = get_supabase_client()
    
    # Verificar si el usuario está aprobado en al menos un negocio
    approved_businesses = supabase.table("usuarios_negocios") \
        .select("id") \
        .eq("usuario_id", user_id) \
        .eq("estado", "aceptado") \
        .execute()
    
    return len(approved_businesses.data or []) > 0

async def get_current_user_with_access_check(request: Request) -> UserData:
    """Obtener usuario actual y verificar que tiene acceso aprobado."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated."
        )
    
    # Verificar acceso (email confirmado se maneja por Supabase Auth)
    has_access = await verify_user_access(user.id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu cuenta está pendiente de aprobación por el administrador del negocio."
        )
    
    return user

security = HTTPBearer()

async def get_current_user_from_request(request: Request) -> User:
    """Get current user from request state (set by auth middleware)"""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

async def verify_business_access(business_id: str, user: User) -> dict:
    """Verificar que el usuario tiene acceso al negocio y devolver información de acceso"""
    supabase = get_supabase_client()
    
    access_response = supabase.table("usuarios_negocios") \
        .select("id, rol, estado") \
        .eq("usuario_id", user.id) \
        .eq("negocio_id", business_id) \
        .eq("estado", "aceptado") \
        .execute()
    
    if not access_response.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este negocio o tu acceso está pendiente de aprobación."
        )
    
    return access_response.data[0]

async def verify_module_permission(business_id: str, user: User, module: str, action: str = "ver") -> dict:
    """
    Verificar que el usuario tiene permisos para un módulo específico
    
    Args:
        business_id: ID del negocio
        user: Usuario actual
        module: Módulo (productos, clientes, categorias, ventas, stock, facturacion, tareas)
        action: Acción (ver, editar, eliminar)
    """
    # Primero verificar acceso al negocio
    business_access = await verify_business_access(business_id, user)
    
    # Si es admin, tiene acceso total
    if business_access["rol"] == "admin":
        return business_access
    
    # Para empleados, verificar permisos específicos
    supabase = get_supabase_client()
    
    permisos_response = supabase.table("permisos_usuario_negocio") \
        .select("*") \
        .eq("usuario_negocio_id", business_access["id"]) \
        .execute()
    
    if not permisos_response.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No tienes permisos configurados para este negocio. Contacta al administrador."
        )
    
    permisos = permisos_response.data[0]
    
    # Verificar acceso total
    if permisos.get("acceso_total"):
        return business_access
    
    # Verificar permiso específico del módulo
    permission_key = f"puede_{action}_{module}"
    
    if not permisos.get(permission_key, False):
        action_text = {
            "ver": "ver",
            "editar": "editar", 
            "eliminar": "eliminar"
        }.get(action, action)
        
        module_text = {
            "productos": "productos",
            "clientes": "clientes", 
            "categorias": "categorías",
            "ventas": "ventas",
            "stock": "inventario",
            "facturacion": "facturación",
            "tareas": "tareas"
        }.get(module, module)
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No tienes permisos para {action_text} {module_text}. Contacta al administrador para solicitar acceso."
        )
    
    return business_access

# Funciones específicas para cada módulo
async def verify_productos_access(business_id: str, user: User, action: str = "ver"):
    return await verify_module_permission(business_id, user, "productos", action)

async def verify_clientes_access(business_id: str, user: User, action: str = "ver"):
    return await verify_module_permission(business_id, user, "clientes", action)

async def verify_categorias_access(business_id: str, user: User, action: str = "ver"):
    return await verify_module_permission(business_id, user, "categorias", action)

async def verify_ventas_access(business_id: str, user: User, action: str = "ver"):
    return await verify_module_permission(business_id, user, "ventas", action)

async def verify_stock_access(business_id: str, user: User, action: str = "ver"):
    return await verify_module_permission(business_id, user, "stock", action)

async def verify_facturacion_access(business_id: str, user: User, action: str = "ver"):
    return await verify_module_permission(business_id, user, "facturacion", action)

async def verify_tareas_access(business_id: str, user: User, action: str = "ver"):
    """Verificar acceso a tareas con permisos específicos"""
    return await verify_module_permission(business_id, user, "tareas", action)

async def verify_basic_business_access(business_id: str, user: User) -> dict:
    """
    Verificar acceso básico al negocio para tareas.
    Permite a todos los usuarios del negocio ver tareas, pero filtra según el rol.
    """
    return await verify_business_access(business_id, user)

async def get_current_tenant_id(current_user: UserData = Depends(get_current_user)) -> str:
    """
    Get the current tenant ID from the authenticated user.
    For now, return a default tenant ID.
    """
    # TODO: Implement proper tenant ID extraction from user context
    return "default_tenant"