"""
auth.py — Endpoints de autenticación local
============================================
FASE 2: Auth 100% local. Sin Supabase Auth.

Endpoints:
  POST /auth/login   → verifica password con bcrypt, devuelve JWT firmado localmente
  POST /auth/logout  → invalida sesión (simple, sin blacklist en esta versión)
  GET  /auth/me      → devuelve datos del usuario logueado (desde JWT + DB)
  POST /auth/setup   → crea el primer y único usuario + negocio (ver FASE 2, paso 4)
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.models.orm_models import Negocio, Usuario
from app.schemas.user import Token

router = APIRouter()

# ---------------------------------------------------------------------------
# Utilidades de seguridad
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una contraseña en texto plano contra su hash bcrypt."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Genera el hash bcrypt de una contraseña."""
    return pwd_context.hash(password)


def create_access_token(user_id: str, email: str) -> str:
    """
    Crea un JWT firmado localmente con HS256.
    El token expira según JWT_ACCESS_TOKEN_EXPIRE_MINUTES en settings.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": user_id,          # subject: ID del usuario
        "email": email,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decodifica y valida un JWT local.
    Lanza HTTPException 401 si el token es inválido o expiró.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión expiró. Volvé a ingresar.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# Schemas de request/response locales (solo los que se usan aquí)
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    """Body del endpoint de login (acepta email o username)."""
    email: Optional[str] = None
    username: Optional[str] = None   # alias para compatibilidad OAuth2 form
    password: str

    @property
    def resolved_email(self) -> str:
        """Retorna el email resolviendo el alias username."""
        return (self.email or self.username or "").strip()


class SetupRequest(BaseModel):
    """Datos para el wizard de primer uso (POST /auth/setup)."""
    nombre_negocio: str
    nombre: str
    apellido: str
    email: str
    password: str


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=Token)
async def login(request: Request, db: Session = Depends(get_db)) -> Any:
    """
    Autenticación local con email + password.

    - Acepta JSON `{email, password}` o form-data OAuth2 `{username, password}`.
    - Verifica la contraseña con bcrypt.
    - Devuelve un JWT firmado localmente (HS256).
    """
    # 1. Parsear body — soportar JSON y form-data
    username: Optional[str] = None
    password: Optional[str] = None

    content_type = request.headers.get("content-type", "")
    try:
        if "application/json" in content_type:
            body = await request.json()
            username = str(body.get("email") or body.get("username") or "").strip() or None
            password = str(body.get("password") or "").strip() or None
        else:
            form = await request.form()
            u = form.get("username") or form.get("email")
            p = form.get("password")
            username = str(u).strip() if isinstance(u, str) else None
            password = str(p).strip() if isinstance(p, str) else None
    except Exception as parse_err:
        print(f"[login] Error parseando body: {parse_err}")

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email y contraseña son requeridos.",
        )

    print(f"[login] Intento de login para: {username}")

    # 2. Buscar usuario en DB local
    usuario = db.query(Usuario).filter(
        Usuario.email == username.lower(),
        Usuario.is_active == True,
    ).first()

    if not usuario or not verify_password(password, usuario.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Actualizar último acceso (best-effort)
    try:
        usuario.ultimo_acceso = datetime.now(timezone.utc)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[login] Advertencia: no se pudo actualizar ultimo_acceso: {e}")

    # 4. Generar y devolver JWT
    token = create_access_token(user_id=usuario.id, email=usuario.email)
    print(f"[login] Login exitoso para user_id={usuario.id}")
    return {"access_token": token, "token_type": "bearer"}


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------

@router.post("/logout")
async def logout() -> dict:
    """
    Cierre de sesión.

    En esta versión desktop (single-user, sin blacklist), el logout es
    responsabilidad del cliente: simplemente descarta el token del storage.
    El endpoint existe para mantener compatibilidad con el frontend.
    """
    return {"message": "Sesión cerrada correctamente."}


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------

@router.get("/me", response_model=dict)
async def get_me(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Any:
    """
    Devuelve los datos del usuario actualmente logueado.

    Valida el JWT localmente y consulta la DB para retornar el perfil completo.
    """
    # 1. Decodificar y validar JWT
    payload = decode_access_token(token)
    user_id: Optional[str] = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token malformado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Cargar usuario desde DB
    usuario = db.query(Usuario).filter(
        Usuario.id == user_id,
        Usuario.is_active == True,
    ).first()

    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado o inactivo.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Construir respuesta (compatible con el frontend existente)
    return {
        "id": usuario.id,
        "email": usuario.email,
        "nombre": usuario.nombre,
        "apellido": usuario.apellido,
        "negocio_id": usuario.negocio_id,
        "is_active": usuario.is_active,
        "is_superuser": usuario.is_superuser,
        "onboarding_completed": usuario.onboarding_completed,
        "creado_en": usuario.creado_en.isoformat() if usuario.creado_en else None,
        "ultimo_acceso": usuario.ultimo_acceso.isoformat() if usuario.ultimo_acceso else None,
        # Campos legacy para compatibilidad con el frontend existente
        "activo": usuario.is_active,
        "rol": "admin" if usuario.is_superuser else "usuario",
        "permisos": [],
    }


# ---------------------------------------------------------------------------
# POST /auth/setup  (FASE 2 — paso 4)
# ---------------------------------------------------------------------------

@router.post("/setup", response_model=Token, status_code=status.HTTP_201_CREATED)
async def setup_initial_user(
    data: SetupRequest,
    db: Session = Depends(get_db),
) -> Any:
    """
    Wizard de primer uso: crea el primer usuario + negocio.

    - Solo funciona si NO existe ningún usuario en la DB.
    - Crea el negocio con el nombre proporcionado.
    - Hashea la contraseña con bcrypt.
    - Devuelve un JWT para que el usuario quede logueado inmediatamente.
    """
    # Protección: si ya existe un usuario, el setup está bloqueado
    existing = db.query(Usuario).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El sistema ya fue configurado. Usá el login normal.",
        )

    # Crear negocio
    negocio = Negocio(
        nombre=data.nombre_negocio.strip(),
    )
    db.add(negocio)
    db.flush()  # Necesario para obtener negocio.id antes del commit

    # Crear usuario administrador
    usuario = Usuario(
        negocio_id=negocio.id,
        email=data.email.strip().lower(),
        nombre=data.nombre.strip(),
        apellido=data.apellido.strip(),
        hashed_password=get_password_hash(data.password),
        is_active=True,
        is_superuser=True,
        onboarding_completed=False,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)

    print(f"[setup] Usuario inicial creado: {usuario.email} (negocio: {negocio.nombre})")

    token = create_access_token(user_id=usuario.id, email=usuario.email)
    return {"access_token": token, "token_type": "bearer"}


# ---------------------------------------------------------------------------
# POST /auth/signup  (Soporte para el registro del Frontend)
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    """Cuerpo esperado por el frontend original en Register.jsx (POST /auth/signup)."""
    email: str
    password: str
    nombre: str
    apellido: str


@router.post("/signup", response_model=Token, status_code=status.HTTP_201_CREATED)
async def signup_fallback_setup(
    data: SignupRequest,
    db: Session = Depends(get_db),
) -> Any:
    """
    Endpoint interceptor para el registro del frontend.
    
    Permite que la pantalla /register original funcione sin tirar 404.
    Dado que es una versión desktop de instalación única:
      - Si ya existe un usuario, bloquea nuevos registros.
      - Si está vacía, inicializa automáticamente el negocio por defecto
        ("Mi Negocio Local") y asocia al usuario administrador a él.
    """
    # 1. Verificar si ya fue configurado
    existing = db.query(Usuario).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La aplicación ya fue inicializada. Por favor ingresá con tu usuario.",
        )

    # 2. Crear negocio por defecto
    negocio = Negocio(
        nombre="Mi Negocio Local",
        descripcion="Inicializado localmente",
    )
    db.add(negocio)
    db.flush()

    # 3. Crear usuario administrador
    usuario = Usuario(
        negocio_id=negocio.id,
        email=data.email.strip().lower(),
        nombre=data.nombre.strip(),
        apellido=data.apellido.strip(),
        hashed_password=get_password_hash(data.password),
        is_active=True,
        is_superuser=True,
        onboarding_completed=True,  # Ya salta el onboarding del cloud
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)

    print(f"[signup-fallback] Negocio creado automáticamente y usuario inicial registrado: {usuario.email}")

    # 4. Generar y devolver token
    token = create_access_token(user_id=usuario.id, email=usuario.email)
    return {"access_token": token, "token_type": "bearer"}

