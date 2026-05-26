"""
deps.py — Dependencias de FastAPI
===================================
FASE 2: Auth 100% local. Sin Supabase.

En la versión desktop el sistema tiene:
  - Un único negocio por instalación.
  - Un único usuario (el dueño del negocio) con rol "admin".
  - Sin RLS ni permisos multi-tenant.

Por eso las funciones de verificación de acceso se simplifican:
la única pregunta es "¿el token es válido y el usuario está activo?".
Las interfaces públicas (firmas de funciones) se mantienen para no
romper los endpoints existentes mientras se migran en la Fase 3.
"""

from typing import Any, Dict, Optional, TypedDict
import logging

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.orm_models import Usuario
from app.types.auth import User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------

class UserData(TypedDict):
    id: str
    email: Optional[str]
    nombre: Optional[str]
    apellido: Optional[str]
    negocio_id: Optional[str]
    activo: bool
    is_active: bool
    is_superuser: bool
    rol: str
    onboarding_completed: bool
    permisos: list


# ---------------------------------------------------------------------------
# Esquemas de seguridad
# ---------------------------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
security = HTTPBearer()


# ---------------------------------------------------------------------------
# get_db — re-exportado para que otros módulos puedan importar desde deps
# ---------------------------------------------------------------------------

# (ya importado arriba: from app.db.session import get_db)


# ---------------------------------------------------------------------------
# get_current_user  ← DEPENDENCIA PRINCIPAL
# ---------------------------------------------------------------------------

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> UserData:
    """
    Valida el JWT local (HS256) y devuelve el perfil del usuario desde SQLite.
    FASE 2: 100% local, sin Supabase Auth.

    Lanza HTTP 401 si:
    - El token es inválido o está expirado.
    - El usuario no existe o está desactivado.
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. Decodificar JWT
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id: Optional[str] = payload.get("sub")
        if not user_id:
            raise credentials_exc
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión expiró. Volvé a ingresar.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise credentials_exc

    # 2. Cargar usuario desde SQLite
    usuario = db.query(Usuario).filter(
        Usuario.id == user_id,
        Usuario.is_active == True,
    ).first()

    if not usuario:
        raise credentials_exc

    logger.debug("[auth] Usuario autenticado: id=%s email=%s", usuario.id, usuario.email)

    # 3. Construir UserData (compatible con el frontend existente)
    return {
        "id": usuario.id,
        "email": usuario.email,
        "nombre": usuario.nombre,
        "apellido": usuario.apellido,
        "negocio_id": usuario.negocio_id,
        "activo": usuario.is_active,
        "is_active": usuario.is_active,
        "is_superuser": usuario.is_superuser,
        "rol": "admin" if usuario.is_superuser else "usuario",
        "onboarding_completed": usuario.onboarding_completed,
        "permisos": [],
    }


# ---------------------------------------------------------------------------
# Dependencias de conveniencia
# ---------------------------------------------------------------------------

async def get_current_active_user(
    current_user: UserData = Depends(get_current_user),
) -> UserData:
    """Igual a get_current_user pero falla con 403 si el usuario está inactivo."""
    if not current_user.get("activo", True):
        raise HTTPException(status_code=403, detail="Usuario inactivo.")
    return current_user


async def get_admin_user(
    current_user: UserData = Depends(get_current_active_user),
) -> UserData:
    """Solo permite el paso a usuarios con rol 'admin'."""
    if current_user.get("rol") != "admin":
        raise HTTPException(status_code=403, detail="Se requieren permisos de administrador.")
    return current_user


async def get_current_tenant_id(
    current_user: UserData = Depends(get_current_user),
) -> str:
    """Retorna el negocio_id del usuario autenticado (single-tenant desktop)."""
    negocio_id = current_user.get("negocio_id") or "default_tenant"
    return str(negocio_id)


# ---------------------------------------------------------------------------
# Helpers de request
# ---------------------------------------------------------------------------

def get_token_from_request(request: Request) -> str:
    """Extrae el Bearer token del header Authorization. Retorna '' si no hay."""
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return ""
    return authorization.replace("Bearer ", "").strip()


async def get_current_user_from_request(request: Request) -> User:
    """
    Obtiene el usuario desde request.state.user (inyectado por middleware).
    Usado en endpoints que procesan el user antes de llegar al handler.
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado.")
    return user  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Verificación de acceso al negocio
# ---------------------------------------------------------------------------
# En la versión desktop hay un único negocio y un único usuario (admin).
# Las funciones de verificación se mantienen con la misma firma para no
# romper los endpoints existentes, pero la lógica se simplifica:
# si el usuario está autenticado → tiene acceso al negocio.
#
# En la Fase 3 (migración de endpoints), se puede refinar si se decide
# agregar múltiples usuarios en el futuro.

def _resolve_user_id(user: Any) -> str:
    """Extrae el ID de usuario independientemente del tipo (dict o objeto)."""
    try:
        if isinstance(user, dict):
            return str(user.get("id", ""))
        return str(getattr(user, "id", ""))
    except Exception:
        return ""


async def verify_business_access(
    business_id: str,
    user: Any,
    authorization: Optional[str] = None,
) -> dict:
    """
    Verifica que el usuario autenticado tenga acceso al negocio indicado.

    Desktop (single-tenant): el usuario siempre es admin de su único negocio.
    Se valida que business_id coincida con el negocio_id del usuario.
    Mantiene la firma original para compatibilidad con los endpoints existentes.
    """
    user_id = _resolve_user_id(user)
    user_negocio = user.get("negocio_id") if isinstance(user, dict) else getattr(user, "negocio_id", None)

    logger.debug(
        "[access] verify_business_access user=%s business=%s user_negocio=%s",
        user_id, business_id, user_negocio,
    )

    # Aceptar si el negocio coincide o si el usuario es superusuario
    is_superuser = (
        user.get("is_superuser") if isinstance(user, dict)
        else getattr(user, "is_superuser", False)
    )

    if user_negocio and str(user_negocio) != str(business_id) and not is_superuser:
        logger.warning(
            "[access] Denied: user=%s tiene negocio=%s pero solicitó business=%s",
            user_id, user_negocio, business_id,
        )
        raise HTTPException(status_code=403, detail="Sin acceso al negocio.")

    # Retorna un dict con la misma forma que retornaba la versión Supabase
    rol = "admin" if is_superuser else (
        user.get("rol") if isinstance(user, dict) else getattr(user, "rol", "usuario")
    )
    return {"id": user_id, "rol": rol, "estado": "aceptado"}


async def verify_user_access(user_id: str, token: str) -> bool:
    """
    Verifica que el token pertenezca al user_id dado.
    Desktop: basta con que el token sea válido (get_current_user ya lo garantiza).
    Se mantiene por compatibilidad; retorna True si hay token.
    """
    return bool(token)


async def get_current_user_with_access_check(request: Request) -> UserData:
    """
    Versión legacy: obtiene el usuario desde request.state y verifica acceso.
    Desktop: si el usuario está en request.state, ya pasó por el middleware de auth.
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado.")
    return user  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Verificación de permisos por módulo
# ---------------------------------------------------------------------------

async def verify_module_permission(
    business_id: str,
    user: Any,
    module: str,
    action: str = "ver",
    authorization: Optional[str] = None,
) -> dict:
    """
    Verifica permiso sobre un módulo específico.

    Desktop (single-user admin): el único usuario tiene acceso total.
    Se mantiene la firma para compatibilidad con los endpoints existentes.
    """
    access = await verify_business_access(business_id, user, authorization)

    logger.debug(
        "[perm] verify_module_permission user=%s business=%s module=%s action=%s rol=%s",
        _resolve_user_id(user), business_id, module, action, access.get("rol"),
    )

    # En desktop el usuario es siempre admin → acceso total
    return access


# ---------------------------------------------------------------------------
# Wrappers por módulo  (mantienen interfaz pública sin cambios)
# ---------------------------------------------------------------------------

async def verify_productos_access(
    business_id: str, user: Any, action: str = "ver", authorization: Optional[str] = None
) -> dict:
    return await verify_module_permission(business_id, user, "productos", action, authorization)

async def verify_clientes_access(
    business_id: str, user: Any, action: str = "ver", authorization: Optional[str] = None
) -> dict:
    return await verify_module_permission(business_id, user, "clientes", action, authorization)

async def verify_categorias_access(
    business_id: str, user: Any, action: str = "ver", authorization: Optional[str] = None
) -> dict:
    return await verify_module_permission(business_id, user, "categorias", action, authorization)

async def verify_ventas_access(
    business_id: str, user: Any, action: str = "ver", authorization: Optional[str] = None
) -> dict:
    return await verify_module_permission(business_id, user, "ventas", action, authorization)

async def verify_stock_access(
    business_id: str, user: Any, action: str = "ver", authorization: Optional[str] = None
) -> dict:
    return await verify_module_permission(business_id, user, "stock", action, authorization)

async def verify_facturacion_access(
    business_id: str, user: Any, action: str = "ver", authorization: Optional[str] = None
) -> dict:
    return await verify_module_permission(business_id, user, "facturacion", action, authorization)

async def verify_tareas_access(
    business_id: str, user: Any, action: str = "ver", authorization: Optional[str] = None
) -> dict:
    return await verify_module_permission(business_id, user, "tareas", action, authorization)

async def verify_basic_business_access(
    business_id: str, user: Any, authorization: Optional[str] = None
) -> dict:
    return await verify_business_access(business_id, user, authorization)