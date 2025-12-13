from typing import Any, Optional, Dict, cast
import uuid
import json
import time
import traceback
import asyncio
import sys
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, status, Request, Body, Depends, UploadFile
from app.db.supabase_client import get_supabase_client, get_supabase_anon_client, get_supabase_user_client
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import EmailStr, ValidationError
import jwt
import requests

from app.db.supabase_client import get_supabase_client, get_supabase_anon_client
from app.core.config import settings
from app.types.auth import Token, UserLogin, UserSignUp, SignUpResponse
from app.core.supabase_admin import supabase_admin

router = APIRouter()

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# JWT Secret para firma de tokens
JWT_SECRET = settings.JWT_SECRET_KEY

def generate_token(user_id: str, email: str) -> str:
    """Generar un token JWT para el usuario"""
    expires = int(time.time()) + 3600 * 24 * 7  # 7 días
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": expires
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return token


@router.post("/login", response_model=Token)
async def login(request: Request) -> Any:
    """
    OAuth2 compatible token login.
    Maneja manualmente el body para evitar errores 422 de Pydantic que rompen el frontend.
    """
    try:
        print("=== Iniciando proceso de login (Robust) ===")
        username: Optional[str] = None
        password: Optional[str] = None

        # 1. Intentar leer como JSON o Form Data
        content_type = request.headers.get("content-type", "")
        
        try:
            if "application/json" in content_type:
                payload = await request.json()
                if isinstance(payload, dict):
                    # Soportar tanto 'username' como 'email'
                    u_val = payload.get("username") or payload.get("email")
                    p_val = payload.get("password")
                    
                    # Asegurar que sean strings
                    username = str(u_val) if u_val else None
                    password = str(p_val) if p_val else None
            else:
                # Form data fallback
                form = await request.form()
                
                # Solución de tipos: Extraer y asegurar que no son UploadFile
                u_form = form.get("username") or form.get("email")
                p_form = form.get("password")
                
                # Si es un string, lo usamos. Si es None o UploadFile, lo ignoramos/manejamos.
                if isinstance(u_form, str):
                    username = u_form
                
                if isinstance(p_form, str):
                    password = p_form

        except Exception as parse_error:
            print(f"Error parseando entrada login: {parse_error}")
        
        # 2. Validación manual para devolver mensaje simple (evita React Error #31)
        if not username or not password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Por favor ingresa tu email y contraseña.",
            )

        print(f"Login solicitado para: {username}")

        # 3. Autenticación con Supabase
        supabase = get_supabase_anon_client()
        
        try:
            # sign_in_with_password es el método correcto en supabase-py v2
            response = supabase.auth.sign_in_with_password({
                "email": username,
                "password": password,
            })

            if not response or not response.session:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Credenciales inválidas.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            print("Login exitoso en Supabase.")
            access_token = response.session.access_token
            # print(f"Access token generado (primeros 10 chars): {access_token[:10]}...") # Security: Don't log tokens
            print(f"User ID: {response.user.id if response.user else 'N/A'}")
            print(f"User email: {response.user.email if response.user else 'N/A'}")

            # Actualizar último acceso (Best effort, no bloquear si falla)
            try:
                if response.user:
                    user_id = response.user.id
                    now = datetime.now(timezone.utc).isoformat()
                    supabase.table("usuarios").update({"ultimo_acceso": now}).eq("id", user_id).execute()
                    print(f"Último acceso actualizado para user_id: {user_id}")
            except Exception as e:
                print(f"Advertencia (no crítica): Error actualizando ultimo_acceso: {str(e)}")

            print("=== Login completado exitosamente, devolviendo token ===")
            return {
                "access_token": access_token,
                "token_type": "bearer"
            }

        except Exception as supabase_error:
            # Capturar errores específicos de Supabase Auth
            error_msg = str(supabase_error).lower()
            print(f"Error Supabase Auth: {error_msg}")

            if "email not confirmed" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Email no confirmado. Revisa tu correo para activar la cuenta."
                )
            elif "invalid login credentials" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Email o contraseña incorrectos."
                )
            else:
                # Error genérico pero limpio para el frontend
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Error de autenticación: {str(supabase_error)}"
                )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error inesperado en login: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al intentar ingresar."
        )


@router.options("/signup")
async def options_signup():
    """Manejar solicitudes OPTIONS para CORS"""
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
    )


@router.post("/signup", response_model=SignUpResponse)
async def signup(user_data: UserSignUp) -> Any:
    """
    Create new user with the given data
    """
    try:
        print(f"Datos de registro recibidos: {user_data.dict()}")
        
        # 1. Inicializar cliente Supabase (Anon key es suficiente para registro)
        supabase = get_supabase_anon_client()

        # 2. Preparar datos de registro
        credentials = {
            "email": user_data.email,
            "password": user_data.password,
            "options": {
                "data": {
                    "nombre": user_data.nombre,
                    "apellido": user_data.apellido,
                },
                "emailRedirectTo": settings.FRONTEND_CONFIRMATION_URL
            }
        }

        # 3. Registrar usuario en Supabase Auth
        auth_response = supabase.auth.sign_up(credentials)

        if not auth_response.user or not auth_response.user.id:
            raise Exception("No se obtuvo ID de usuario al registrar en Supabase")

        user_id = auth_response.user.id
        print(f"Usuario creado Auth ID: {user_id}")

        # La creación del perfil en 'usuarios' ahora se maneja vía Trigger en la BD
        # (ver migration 07_create_user_trigger.sql)

        # 4. Configurar periodo de prueba (30 días)
        # Implementamos retries porque el trigger de creación de usuario en public.usuarios
        # puede tener un ligero retraso respecto a auth.users
        try:
            trial_end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
            
            # Verificar si es un usuario exento
            is_exempt = user_data.email in settings.EXEMPT_EMAILS
            
            update_data = {
                "subscription_status": "trial",
                "trial_end": trial_end,
                "is_exempt": is_exempt
            }
            
            print(f"Configurando suscripción para {user_data.email}: {update_data}")
            
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    # Intentamos actualizar. Si el usuario no existe aún en public.usuarios,
                    # response.data estará vacío.
                    response = supabase.table("usuarios").update(update_data).eq("id", user_id).execute()
                    
                    if response.data and len(response.data) > 0:
                        print(f"Suscripción configurada correctamente en intento {attempt + 1}")
                        break
                    else:
                        print(f"Intento {attempt + 1}/{max_retries}: Usuario no encontrado aún en public.usuarios, reintentando...")
                except Exception as e:
                    print(f"Error en intento {attempt + 1}/{max_retries}: {str(e)}")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.0) # Esperar 1 segundo antes del siguiente intento
            else:
                print("ADVERTENCIA: No se pudo configurar la suscripción después de varios intentos. Es posible que el trigger haya fallado.")
            
        except Exception as sub_error:
            print(f"Error configurando suscripción inicial: {sub_error}")
            # No bloqueamos el registro por esto, pero logueamos el error

        if settings.DEBUG:
            message = "Usuario registrado. En desarrollo revisa logs o tabla para confirmar."
            requires_confirmation = False
        else:
            message = "Usuario registrado correctamente. Por favor revisa tu email."
            requires_confirmation = True

        return SignUpResponse(
            message=message,
            email=user_data.email,
            requires_confirmation=requires_confirmation
        )

    except Exception as e:
        print(f"Registration error: {str(e)}")
        error_message = str(e)
        if "User already registered" in error_message or "already been registered" in error_message:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Este email ya está registrado.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al crear usuario: {str(e)}",
        )


@router.get("/me", response_model=dict)
async def read_users_me(request: Request) -> Any:
    """
    Get current user using the user's own token (RLS Safe).
    """
    try:
        print("=== /auth/me LLAMADO ===")
        # 1. Extraer y limpiar el token
        authorization = request.headers.get("Authorization", "")
        print(f"Authorization header presente: {bool(authorization)}")
        if not authorization or not authorization.startswith("Bearer "):
            print("[ERROR] Token no presente o formato incorrecto")
            raise HTTPException(status_code=401, detail="Token requerido")
        
        token = authorization.replace("Bearer ", "")
        # print(f"Token extraído (primeros 10 chars): {token[:10]}...") # Security: Don't log tokens
        
        # 2. Cliente Supabase con token de usuario
        print("Creando cliente Supabase con token de usuario...")
        supabase = get_supabase_user_client(token)
        
        # 3. Validar token
        print("Validando token con Supabase Auth...")
        auth_response = supabase.auth.get_user(token)
        if not auth_response or not auth_response.user:
            print("[ERROR] Token inválido - auth_response vacío")
            raise HTTPException(status_code=401, detail="Token inválido")
            
        user = auth_response.user
        user_id = user.id
        print(f"Usuario autenticado: {user_id}, email: {user.email}")
        
        # 4. Consultar perfil
        print(f"Consultando perfil en tabla usuarios para user_id: {user_id}")
        response = supabase.table("usuarios").select("*").eq("id", user_id).execute()
        print(f"Respuesta de tabla usuarios: {len(response.data) if response.data else 0} registros")
        
        if not response.data:
            print("[FALLBACK] Usuario no encontrado en tabla, devolviendo datos básicos")
            # FALLBACK: Si no existe en la tabla usuarios, devolvemos esto.
            fallback_data = {
                "id": user_id,
                "email": user.email,
                "nombre": "",
                "apellido": "",
                "rol": "usuario",
                "activo": True,
                "permisos": [],
                "onboarding_completed": False
            }
            print(f"Datos fallback: {fallback_data}")
            return fallback_data
        
        user_data = response.data[0]
        print(f"Datos de usuario encontrados: {user_data.keys()}")
        
        # Asegurar que permisos sea una lista si es None
        if user_data.get("permisos") is None:
            print("[FIX] Agregando permisos vacíos")
            user_data["permisos"] = []

        # 5. Mezclar datos
        user_data.update({
            "email": user.email,
            "email_confirmed_at": getattr(user, "email_confirmed_at", None),
            "last_sign_in_at": getattr(user, "last_sign_in_at", None),
            "onboarding_completed": user_data.get("onboarding_completed", False)
        })
        
        print(f"[SUCCESS] Devolviendo datos de usuario completos")
        return user_data
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR CRÍTICO] Error inesperado en /auth/me: {str(e)}")
        print(f"Tipo de error: {type(e).__name__}")
        import traceback
        print(f"Traceback completo:\n{traceback.format_exc()}")
        raise HTTPException(status_code=401, detail=f"Error de sesión: {str(e)}")


@router.put("/profile", response_model=dict)
async def update_profile(profile_data: dict, request: Request) -> Any:
    try:
        if not hasattr(request.state, 'user') or not request.state.user:
            raise HTTPException(status_code=401, detail="Usuario no autenticado")
        
        user = request.state.user
        user_id = user.id
        
        allowed_fields = ['nombre', 'apellido', 'telefono']
        update_data = {k: v for k, v in profile_data.items() if k in allowed_fields and v is not None}
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No hay datos válidos para actualizar")
        
        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        
        supabase = get_supabase_client()
        response = supabase.table("usuarios").update(update_data).eq("id", user_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        updated_user = response.data[0]
        updated_user.update({
            "email": user.email
        })
        
        return updated_user
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error update profile: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.put("/change-password", response_model=dict)
async def change_password(password_data: dict, request: Request) -> Any:
    try:
        if not hasattr(request.state, 'user') or not request.state.user:
            raise HTTPException(status_code=401, detail="Usuario no autenticado")
        
        user = request.state.user
        # current_password = password_data.get('currentPassword')
        new_password = password_data.get('newPassword')
        
        if not new_password or len(new_password) < 6:
            raise HTTPException(status_code=400, detail="La nueva contraseña debe tener al menos 6 caracteres")
        
        supabase = get_supabase_client()
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        
        try:
            # Actualizar usuario autenticado
            supabase.auth.update_user({
                "password": new_password
            })
            return {"message": "Contraseña actualizada correctamente"}
            
        except Exception as update_error:
            print(f"Error al actualizar contraseña: {str(update_error)}")
            raise HTTPException(status_code=500, detail="Error al actualizar la contraseña")
        
    except HTTPException:
        raise


@router.post("/resend-confirmation")
async def resend_confirmation_email(email_data: Dict[str, str] = Body(...)) -> Any:
    """
    Reenviar email de confirmación usando sign_in_with_otp (Magic Link).
    Esta es la forma compatible con supabase-py v2 para verificar emails no confirmados.
    """
    try:
        email = email_data.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email es requerido"
            )
        
        supabase = get_supabase_client()
        
        # Verificar existencia local primero
        user_check = supabase.table("usuarios").select("id").eq("email", email).execute()
        if not user_check.data:
             raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )

        try:
            # SOLUCIÓN PRINCIPAL AL ERROR 'resend_method':
            # Usamos sign_in_with_otp. Esto envía un Magic Link.
            print(f"Enviando OTP/Magic Link a {email} para verificación...")
            supabase.auth.sign_in_with_otp({
                "email": email
            })
            
            return {
                "message": "Email de confirmación reenviado correctamente (Magic Link)",
                "email": email
            }
            
        except Exception as auth_error:
            error_message = str(auth_error)
            print(f"Error enviando OTP: {error_message}")
            
            if "Email already confirmed" in error_message:
                return {
                    "message": "El email ya está confirmado",
                    "email": email,
                    "already_confirmed": True
                }
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error al reenviar correo: {error_message}"
            )
                
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error interno resend: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )


@router.get("/confirm")
async def confirm_redirect():
    """Redirige confirmaciones al frontend"""
    return RedirectResponse(url=settings.FRONTEND_CONFIRMATION_URL)


@router.post("/verify-email")
async def verify_email(data: Dict[str, str] = Body(...)) -> Any:
    """
    Verifica el token_hash del correo (PKCE flow).
    """
    try:
        token_hash = data.get("token_hash")
        type_ = data.get("type", "email")

        if not token_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token hash es requerido"
            )

        supabase = get_supabase_anon_client()
        
        # Verificar OTP con Supabase
        response = supabase.auth.verify_otp({
            "token_hash": token_hash,
            "type": type_
        })

        if not response.session:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error al verificar el token o sesión no creada."
            )

        return {
            "message": "Email verificado correctamente",
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "user": {
                "id": response.user.id,
                "email": response.user.email
            }
        }

    except Exception as e:
        print(f"Error verifying email: {str(e)}")
        error_msg = str(e).lower()
        if "expired" in error_msg:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El enlace ha expirado."
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Error al verificar el email."
        )


@router.get("/check-confirmation/{email}")
async def check_email_confirmation(email: str) -> Any:
    """
    Verificar estado real de confirmación consultando auth.users via Admin API.
    """
    try:
        # 1. Obtener ID del usuario desde tabla pública
        supabase = get_supabase_client()
        user_query = supabase.table("usuarios").select("id").eq("email", email).execute()
        
        if not user_query.data:
            # Usuario no existe en tabla pública
            return {"email": email, "is_confirmed": False, "message": "Usuario no encontrado"}
            
        user_id = user_query.data[0]["id"]
        
        # 2. Consultar estado en auth.users usando Admin API
        auth_user = await supabase_admin.get_auth_user(user_id)
        
        if not auth_user:
             return {"email": email, "is_confirmed": False, "message": "Error al consultar estado"}
             
        email_confirmed_at = auth_user.get("email_confirmed_at")
        
        if email_confirmed_at:
            return {"email": email, "is_confirmed": True, "message": "Confirmado"}
        else:
            return {"email": email, "is_confirmed": False, "message": "Pendiente de confirmación"}

    except Exception as e:
        print(f"Check confirmation error: {e}")
        # No devolver 500 para no romper el frontend, sino estado desconocido/falso
        return {"email": email, "is_confirmed": False, "message": "Error verificando estado"}


@router.delete("/users/{user_id}")
async def delete_user_completely(user_id: str, request: Request) -> Any:
    """Eliminar usuario (Self-deletion o Admin)"""
    try:
        current_user = getattr(request.state, "user", None)
        if not current_user:
            raise HTTPException(status_code=401, detail="Usuario no autenticado")
        
        if current_user.id != user_id:
             raise HTTPException(status_code=403, detail="No tienes permisos para eliminar este usuario")
        
        supabase = get_supabase_client()
        
        # Eliminar de tabla pública
        supabase.table("usuarios").delete().eq("id", user_id).execute()
        
        return {"message": "Usuario eliminado correctamente"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error delete user: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno al eliminar usuario")

@router.post("/complete-onboarding", response_model=dict)
async def complete_onboarding(request: Request) -> Any:
    """
    Marcar el onboarding como completado para el usuario actual.
    """
    try:
        if not hasattr(request.state, 'user') or not request.state.user:
            raise HTTPException(status_code=401, detail="Usuario no autenticado")
        
        user = request.state.user
        user_id = user.id
        
        supabase = get_supabase_client()
        
        # Actualizar flag en la base de datos
        response = supabase.table("usuarios").update({"onboarding_completed": True}).eq("id", user_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Usuario no encontrado al actualizar onboarding")
            
        return {"message": "Onboarding completado", "onboarding_completed": True}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error completing onboarding: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al completar el onboarding")