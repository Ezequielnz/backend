from typing import Any, Dict, Optional, cast
import uuid
import json
import time
import traceback
import sys
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status, Request, BackgroundTasks, Depends
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import EmailStr, ValidationError
import jwt
import requests

from app.db.supabase_client import get_supabase_client, get_supabase_anon_client, get_supabase_user_client
from app.core.config import settings
from app.types.auth import Token, UserLogin, UserSignUp, SignUpResponse
from app.core.supabase_admin import supabase_admin

# Inicializar logger
logger = logging.getLogger(__name__)

router = APIRouter()

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# JWT Secret para firma de tokens
JWT_SECRET = "micropymes_secret_key"

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

# Función auxiliar para tarea en segundo plano
def update_user_last_access(user_id: str):
    try:
        supabase = get_supabase_client()
        now = datetime.now(timezone.utc).isoformat()
        supabase.table("usuarios").update({"ultimo_acceso": now}).eq("id", user_id).execute()
        logger.info(f"Éxito. Actualizado último acceso para usuario {user_id}")
    except Exception as e:
        logger.warning(f"Advertencia: Error al actualizar último acceso: {str(e)}")

@router.post("/login", response_model=Token)
async def login(
    login_data: UserLogin,
    background_tasks: BackgroundTasks
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests.
    """
    try:
        logger.info("=== Iniciando proceso de login ===")
        
        username = login_data.email
        password = login_data.password

        logger.info(f"Email recibido: {username}")

        supabase = get_supabase_client()
        logger.info("Intentando iniciar sesión con Supabase...")
        
        try:
            response = supabase.auth.sign_in_with_password({
                "email": username,
                "password": password,
            })

            if not response or not response.session:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Credenciales inválidas",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            logger.info("Éxito. Respuesta de Supabase recibida")
            logger.info(f"Usuario ID: {response.user.id if response.user else 'No ID'}")

            access_token = response.session.access_token
            
            if response.user:
                background_tasks.add_task(update_user_last_access, response.user.id)

            return {
                "access_token": access_token,
                "token_type": "bearer"
            }
            
        except Exception as supabase_error:
            logger.error(f"Error en Supabase Auth: {supabase_error}")
            
            error_message = str(supabase_error)
            if "Email not confirmed" in error_message:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "message": "Email no confirmado. Por favor revisa tu correo electrónico para activar tu cuenta.",
                        "error_type": "email_not_confirmed",
                        "email": username
                    }
                )
            elif "Invalid login credentials" in error_message:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Credenciales inválidas",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Error al iniciar sesión: {error_message}",
                    headers={"WWW-Authenticate": "Bearer"},
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error general en login: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor",
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
        logger.info(f"Datos de registro recibidos: {user_data.model_dump()}")

        supabase = get_supabase_anon_client()

        logger.info("Registrando usuario en Supabase Auth...")
        
        signup_options: Dict[str, Any] = {
            "email": user_data.email,
            "password": user_data.password,
        }
        
        if settings.DEBUG:
            logger.info("🔧 MODO DEBUG: Deshabilitando confirmación de email")
            signup_options["options"] = {
                "email_confirm": False
            }
        
        # cast(Any, ...) evita errores de tipado estricto con el diccionario
        auth_response = supabase.auth.sign_up(cast(Any, signup_options))

        if not auth_response.user or not auth_response.user.id:
            raise Exception("Error al crear usuario en Supabase Auth - no se obtuvo ID de usuario")

        user_id = auth_response.user.id
        logger.info(f"Usuario creado en Supabase Auth con ID: {user_id}")

        now = datetime.now(timezone.utc).isoformat()

        user_profile = {
            "id": user_id,
            "email": user_data.email,
            "nombre": user_data.nombre,
            "apellido": user_data.apellido,
            "creado_en": now,
            "ultimo_acceso": now
        }
        response = supabase.table("usuarios").insert(user_profile).execute()
        logger.info(f"Perfil creado en tabla usuarios: {response.data}")

        if settings.DEBUG:
            message = "Usuario registrado correctamente. En modo desarrollo, no se requiere confirmación de email."
            requires_confirmation = False
        else:
            message = "Usuario registrado correctamente. Por favor revisa tu email para confirmar la cuenta antes de iniciar sesión."
            requires_confirmation = True

        logger.info("✅ Usuario registrado exitosamente.")
        return SignUpResponse(
            message=message,
            email=user_data.email,
            requires_confirmation=requires_confirmation
        )

    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        logger.error(traceback.format_exc())
        error_message = str(e)
        if "User already registered" in error_message or "already been registered" in error_message:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Este email ya está registrado. Si no has confirmado tu cuenta, revisa tu correo electrónico.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al crear usuario: {str(e)}",
        )


@router.get("/me", response_model=dict)
async def read_users_me(request: Request) -> Any:
    try:
        if not hasattr(request.state, 'user') or not request.state.user:
            raise HTTPException(status_code=401, detail="Usuario no autenticado")
        
        user = request.state.user
        user_id = user.id
        
        supabase = get_supabase_client()
        
        response = supabase.table("usuarios").select("*").eq("id", user_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        user_data = response.data[0]
        
        user_data.update({
            "email": user.email,
            "email_confirmed_at": getattr(user, 'email_confirmed_at', None),
            "last_sign_in_at": getattr(user, 'last_sign_in_at', None),
        })
        
        return user_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al obtener información del usuario: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


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
            "email": user.email,
            "email_confirmed_at": getattr(user, 'email_confirmed_at', None),
            "last_sign_in_at": getattr(user, 'last_sign_in_at', None),
        })
        
        return updated_user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al actualizar perfil: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.put("/change-password", response_model=dict)
async def change_password(password_data: dict, request: Request) -> Any:
    try:
        if not hasattr(request.state, 'user') or not request.state.user:
            raise HTTPException(status_code=401, detail="Usuario no autenticado")
        
        user = request.state.user
        current_password = password_data.get('currentPassword')
        new_password = password_data.get('newPassword')
        
        if not current_password or not new_password:
            raise HTTPException(status_code=400, detail="Se requiere la contraseña actual y la nueva contraseña")
        
        if len(new_password) < 6:
            raise HTTPException(status_code=400, detail="La nueva contraseña debe tener al menos 6 caracteres")
        
        supabase = get_supabase_client()
        
        try:
            verify_response = supabase.auth.sign_in_with_password({
                "email": user.email,
                "password": current_password
            })
            
            if not verify_response or not verify_response.session:
                raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta")
                
        except Exception as verify_error:
            if "Invalid login credentials" in str(verify_error):
                raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta")
            else:
                raise HTTPException(status_code=500, detail="Error al verificar la contraseña actual")
        
        try:
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            user_supabase = get_supabase_user_client(token)
            
            user_supabase.auth.update_user({"password": new_password})
            
            return {"message": "Contraseña actualizada correctamente"}
            
        except Exception as update_error:
            logger.error(f"Error al actualizar contraseña: {str(update_error)}")
            raise HTTPException(status_code=500, detail="Error al actualizar la contraseña")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error general al cambiar contraseña: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/activate/{email}")
async def activate_user(email: str) -> Any:
    """
    SOLO PARA DESARROLLO: Activa la cuenta de un usuario
    """
    try:
        if not settings.DEBUG:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Esta función solo está disponible en entorno de desarrollo"
            )
            
        supabase = get_supabase_client()
        
        user_data = supabase.table("usuarios").select("id").eq("email", email).execute()
        
        if not user_data.data or len(user_data.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Usuario con email {email} no encontrado"
            )
            
        user_id = user_data.data[0]["id"]
        
        try:
            headers = {
                "Authorization": f"Bearer {settings.SUPABASE_KEY}",
                "Content-Type": "application/json",
                "apikey": settings.SUPABASE_KEY
            }
            
            admin_url = f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}"
            update_data = {
                "email_confirm": True,
                "email_confirmed_at": datetime.now(timezone.utc).isoformat()
            }
            
            response = requests.put(admin_url, json=update_data, headers=headers)
            
            if response.status_code == 200:
                return {
                    "detail": f"Usuario {email} activado exitosamente",
                    "user_id": user_id,
                    "status": "confirmed"
                }
            else:
                logger.error(f"Error en API admin: {response.status_code} - {response.text}")
                
                now = datetime.now(timezone.utc).isoformat()
                supabase.table("usuarios").update({
                    "email_confirmado": True,
                    "email_confirmado_en": now
                }).eq("id", user_id).execute()
                
                return {
                    "detail": f"Usuario {email} marcado como confirmado en base de datos local",
                    "user_id": user_id,
                    "status": "confirmed_locally",
                    "note": "Para confirmación completa, ve a Supabase Dashboard"
                }
                
        except Exception as admin_error:
            logger.error(f"Error en activación admin: {str(admin_error)}")
            return {
                "detail": "No se pudo activar automáticamente",
                "instrucciones": ["Activar manualmente en Supabase Dashboard"]
            }
        
    except Exception as e:
        logger.error(f"Error en activate_user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al activar usuario: {str(e)}"
        )


@router.get("/confirm")
async def confirm_redirect():
    """Redirige las solicitudes de confirmación al frontend"""
    return RedirectResponse(url=settings.FRONTEND_CONFIRMATION_URL)


@router.get("/check-confirmation/{email}")
async def check_email_confirmation(email: str) -> Any:
    """Verificar si un email ha sido confirmado"""
    try:
        supabase = get_supabase_client()
        
        user_response = supabase.table("usuarios").select("id, email").eq("email", email).execute()
        
        if not user_response.data or len(user_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )
        
        try:
            supabase.auth.sign_in_with_password({
                "email": email,
                "password": "test_password_for_verification"
            })
            return {"email": email, "is_confirmed": True, "message": "Email confirmado"}
            
        except Exception as auth_error:
            error_message = str(auth_error)
            
            if "Email not confirmed" in error_message:
                return {
                    "email": email,
                    "is_confirmed": False,
                    "message": "Email no confirmado. Por favor revisa tu correo electrónico."
                }
            elif "Invalid login credentials" in error_message:
                return {"email": email, "is_confirmed": True, "message": "Email confirmado"}
            else:
                return {
                    "email": email,
                    "is_confirmed": False,
                    "message": f"Error al verificar confirmación: {error_message}"
                }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al verificar confirmación de email: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )


@router.post("/resend-confirmation")
async def resend_confirmation_email(email_data: dict) -> Any:
    """
    Reenviar email de confirmación (usando Magic Link como alternativa compatible)
    """
    try:
        email = email_data.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email es requerido"
            )
        
        supabase = get_supabase_client()
        
        # Verificar que el usuario existe
        user_response = supabase.table("usuarios").select("id, email").eq("email", email).execute()
        
        if not user_response.data or len(user_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )
        
        # Reenviar email de confirmación
        try:
            # CORRECCIÓN: Usar sign_in_with_otp porque 'resend' no existe en esta versión.
            # Esto enviará un Magic Link que sirve para VERIFICAR la cuenta si aún no está confirmada.
            resend_response = supabase.auth.sign_in_with_otp({
                "email": email,
                # Opcional: Configurar la URL de redirección si la tienes en settings
                # "options": {
                #     "email_redirect_to": settings.FRONTEND_URL 
                # }
            })
            
            return {
                "message": "Email de confirmación (Magic Link) reenviado correctamente",
                "email": email
            }
            
        except Exception as resend_error:
            error_message = str(resend_error)
            print(f"Error al reenviar (sign_in_with_otp): {error_message}")
            
            # Manejo específico de errores si es necesario
            if "Email already confirmed" in error_message:
                return {
                    "message": "El email ya está confirmado",
                    "email": email,
                    "already_confirmed": True
                }
            else:
                # Si falla sign_in_with_otp, lanzamos el error
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Error al reenviar confirmación: {error_message}"
                )
                
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error interno en resend-confirmation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )


@router.delete("/users/{user_id}")
async def delete_user_completely(user_id: str, request: Request) -> Any:
    """Eliminar usuario completamente con todos sus datos relacionados."""
    supabase = get_supabase_client()
    try:
        logger.info(f"=== Iniciando eliminación completa del usuario {user_id} ===")
        
        current_user = getattr(request.state, "user", None)
        if not current_user:
            raise HTTPException(status_code=401, detail="Usuario no autenticado")
        
        if current_user.id != user_id:
            admin_check = supabase.table("usuarios_negocios") \
                .select("negocio_id") \
                .eq("usuario_id", current_user.id) \
                .eq("rol", "admin") \
                .eq("estado", "aceptado") \
                .execute()
            
            if not admin_check.data:
                raise HTTPException(status_code=403, detail="No tienes permisos para eliminar este usuario")
            
            admin_business_ids = [item["negocio_id"] for item in admin_check.data]
            user_in_business = supabase.table("usuarios_negocios") \
                .select("negocio_id") \
                .eq("usuario_id", user_id) \
                .in_("negocio_id", admin_business_ids) \
                .execute()
            
            if not user_in_business.data:
                raise HTTPException(status_code=403, detail="No puedes eliminar este usuario")
        
        user_check = supabase.table("usuarios") \
            .select("id, email, nombre, apellido") \
            .eq("id", user_id) \
            .execute()
        
        if not user_check.data:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        user_data = user_check.data[0]
        logger.info(f"Eliminando usuario: {user_data['email']}")
        
        supabase.table("usuarios").delete().eq("id", user_id).execute()
        
        logger.info(f"✅ Usuario {user_data['email']} eliminado completamente")
        
        return {
            "message": "Usuario eliminado completamente",
            "user_id": user_id,
            "email": user_data['email']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error inesperado eliminando usuario: {type(e).__name__} - {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno eliminando usuario: {str(e)}"
        )


@router.delete("/users/by-email/{email}")
async def delete_user_by_email(email: str, request: Request) -> Any:
    """Eliminar usuario por email (útil para desarrollo y testing)."""
    try:
        logger.info(f"=== Buscando usuario por email: {email} ===")
        
        supabase = get_supabase_client()
        
        user_check = supabase.table("usuarios") \
            .select("id, email, nombre, apellido") \
            .eq("email", email) \
            .execute()
        
        if not user_check.data:
            raise HTTPException(status_code=404, detail=f"Usuario con email {email} no encontrado")
        
        user_data = user_check.data[0]
        user_id = user_data["id"]
        
        request.state.user = type('User', (), {'id': user_id})()
        
        logger.info(f"Eliminando usuario: {user_data['email']}")
        
        supabase.table("usuarios").delete().eq("id", user_id).execute()
        
        auth_deleted = await supabase_admin.delete_auth_user(user_id)
        
        logger.info(f"✅ Usuario {user_data['email']} eliminado completamente")
        
        return {
            "message": "Usuario eliminado completamente",
            "user_id": user_id,
            "email": user_data['email'],
            "auth_deletion_success": auth_deleted
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error eliminando usuario por email: {e}")
        raise HTTPException(status_code=500, detail=f"Error eliminando usuario: {str(e)}")