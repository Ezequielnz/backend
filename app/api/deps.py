from typing import Dict, Any, Optional, TypedDict
import logging
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, HTTPBearer

# Importaciones necesarias
from app.db.session import get_db 
from app.db.supabase_client import get_supabase_client, get_supabase_user_client
from app.types.auth import User
from app.core.config import settings

print("--- DEPS.PY RECREADO DESDE CERO ---")

logger = logging.getLogger(__name__)

# Definición de tipos para evitar errores en frontend
class UserData(TypedDict):
    id: str
    email: Optional[str]
    rol: str
    activo: bool
    nombre: Optional[str]
    apellido: Optional[str]

# Esquema OAuth2
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserData:
    """
    Obtiene el usuario actual usando SU PROPIO token para respetar RLS.
    """
    try:
        # 1. Validar token (Cliente Anónimo)
        supabase_anon = get_supabase_client()
        auth_response = supabase_anon.auth.get_user(token)
        
        if not auth_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user_id = auth_response.user.id
        user_email = auth_response.user.email

        # 2. Obtener Perfil (Cliente de Usuario - RLS Safe)
        # Usamos el token del usuario para que Postgres sepa quién hace la consulta
        supabase_user = get_supabase_user_client(token)
        
        user_response = supabase_user.table("usuarios").select("*").eq("id", user_id).execute()
        
        # Si el usuario no existe en la tabla pública, devolvemos datos básicos
        if not user_response.data:
            return {
                "id": user_id,
                "email": user_email,
                "rol": "usuario",
                "activo": True,
                "nombre": "",
                "apellido": ""
            }
            
        return user_response.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error crítico en get_current_user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Error de autenticación",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Dependencias adicionales requeridas por otros endpoints

async def get_current_active_user(current_user: UserData = Depends(get_current_user)) -> UserData:
    if not current_user.get("activo", True):
        raise HTTPException(status_code=403, detail="Usuario inactivo")
    return current_user

async def get_admin_user(current_user: UserData = Depends(get_current_active_user)) -> UserData:
    if current_user.get("rol") != "admin":
        raise HTTPException(status_code=403, detail="Se requieren permisos de administrador")
    return current_user

# Helpers para endpoints que verifican acceso

def get_token_from_request(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return ""
    return authorization.replace("Bearer ", "")

async def verify_user_access(user_id: str, token: str) -> bool:
    if not token: return False
    # Usar cliente de usuario para ver si tiene acceso a sus propios negocios
    supabase = get_supabase_user_client(token)
    try:
        approved = supabase.table("usuarios_negocios").select("id").eq("usuario_id", user_id).eq("estado", "aceptado").execute()
        return len(approved.data or []) > 0
    except: return False

async def get_current_user_with_access_check(request: Request) -> UserData:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    
    token = get_token_from_request(request)
    # Si falla la verificación, lanzamos error
    if not await verify_user_access(user['id'], token):
         raise HTTPException(status_code=403, detail="Cuenta pendiente de aprobación")
    return user

security = HTTPBearer()

def _resolve_user_id(user: Any) -> str:
    try:
        if isinstance(user, dict):
            return str(user.get("id", ""))
        return str(getattr(user, "id", ""))
    except Exception:
        return ""

async def get_current_user_from_request(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    return user

async def verify_business_access(business_id: str, user: User, authorization: Optional[str] = None) -> dict:
    user_id = _resolve_user_id(user)
    token = authorization or getattr(user, "token", None)
    logger.debug(
        "[access] Checking membership user=%s business=%s (token_supplied=%s service_role_configured=%s)",
        user_id,
        business_id,
        bool(token),
        bool(settings.SUPABASE_SERVICE_ROLE_KEY),
    )
    supabase = get_supabase_user_client(token) if token else get_supabase_client()
    try:
        access = (
            supabase.table("usuarios_negocios")
            .select("id, rol, estado")
            .eq("usuario_id", user_id)
            .eq("negocio_id", business_id)
            .eq("estado", "aceptado")
            .execute()
        )
    except Exception as exc:
        logger.exception(
            "[access] Supabase error while checking membership user=%s business=%s: %s",
            user_id,
            business_id,
            exc,
        )
        raise

    row_count = len(access.data or [])
    logger.debug(
        "[access] Membership lookup user=%s business=%s returned %d rows",
        user_id,
        business_id,
        row_count,
    )

    if not access.data:
        logger.warning(
            "[access] Membership missing for user=%s business=%s (RLS active=%s)",
            user_id,
            business_id,
            not bool(settings.SUPABASE_SERVICE_ROLE_KEY),
        )
        raise HTTPException(status_code=403, detail="Sin acceso al negocio")
    return access.data[0]

async def verify_module_permission(
    business_id: str,
    user: User,
    module: str,
    action: str = "ver",
    authorization: Optional[str] = None,
) -> dict:
    access = await verify_business_access(business_id, user, authorization)
    if access["rol"] == "admin":
        logger.debug(
            "[perm] Granting admin override user=%s business=%s module=%s action=%s",
            _resolve_user_id(user),
            business_id,
            module,
            action,
        )
        return access
    
    token = authorization or getattr(user, "token", None)
    supabase = get_supabase_user_client(token) if token else get_supabase_client()
    try:
        perms = (
            supabase.table("permisos_usuario_negocio")
            .select("*")
            .eq("usuario_negocio_id", access["id"])
            .execute()
        )
    except Exception as exc:
        logger.exception(
            "[perm] Supabase error fetching permissions usuario_negocio_id=%s: %s",
            access["id"],
            exc,
        )
        raise
    
    if not perms.data:
        logger.warning(
            "[perm] No permission row for usuario_negocio_id=%s user=%s business=%s",
            access["id"],
            _resolve_user_id(user),
            business_id,
        )
        raise HTTPException(status_code=403, detail="Permisos no configurados")
    
    p = perms.data[0]
    if p.get("acceso_total") or p.get(f"puede_{action}_{module}", False):
        logger.debug(
            "[perm] Permission granted user=%s business=%s module=%s action=%s",
            _resolve_user_id(user),
            business_id,
            module,
            action,
        )
        return access
        
    logger.warning(
        "[perm] Permission denied user=%s business=%s module=%s action=%s acceso_total=%s",
        _resolve_user_id(user),
        business_id,
        module,
        action,
        p.get("acceso_total"),
    )
    raise HTTPException(status_code=403, detail=f"Sin permiso para {action} {module}")

# Wrappers para cada módulo
async def verify_productos_access(business_id: str, user: User, action: str = "ver", authorization: Optional[str] = None): return await verify_module_permission(business_id, user, "productos", action, authorization)
async def verify_clientes_access(business_id: str, user: User, action: str = "ver", authorization: Optional[str] = None): return await verify_module_permission(business_id, user, "clientes", action, authorization)
async def verify_categorias_access(business_id: str, user: User, action: str = "ver", authorization: Optional[str] = None): return await verify_module_permission(business_id, user, "categorias", action, authorization)
async def verify_ventas_access(business_id: str, user: User, action: str = "ver", authorization: Optional[str] = None): return await verify_module_permission(business_id, user, "ventas", action, authorization)
async def verify_stock_access(business_id: str, user: User, action: str = "ver", authorization: Optional[str] = None): return await verify_module_permission(business_id, user, "stock", action, authorization)
async def verify_facturacion_access(business_id: str, user: User, action: str = "ver", authorization: Optional[str] = None): return await verify_module_permission(business_id, user, "facturacion", action, authorization)
async def verify_tareas_access(business_id: str, user: User, action: str = "ver", authorization: Optional[str] = None): return await verify_module_permission(business_id, user, "tareas", action, authorization)
async def verify_basic_business_access(business_id: str, user: User, authorization: Optional[str] = None) -> dict: return await verify_business_access(business_id, user, authorization)
async def get_current_tenant_id(current_user: UserData = Depends(get_current_user)) -> str: return "default_tenant"