from typing import Any, Optional
import uuid
import json
import time
import traceback
import sys
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status, Request
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

# JWT Secret para firma de tokens (en producción debería estar en variables de entorno)
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


@router.post("/login", response_model=Token)
async def login(request: Request) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests.
    Accepts application/x-www-form-urlencoded or JSON payloads.
    """
    try:
        print("=== Iniciando proceso de login ===")
        username: Optional[str] = None
        password: Optional[str] = None

        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            form = await request.form()
            username = form.get("username") or form.get("email")
            password = form.get("password")
        else:
            try:
                payload = await request.json()
            except Exception:
                payload = {}

            if isinstance(payload, dict):
                username = payload.get("username") or payload.get("email")
                password = payload.get("password")

        if not username or not password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Se requieren credenciales (username/email y password) para iniciar sesión.",
            )

        print(f"Email recibido: {username}")

        supabase = get_supabase_client()
        print("Intentando iniciar sesión con Supabase...")
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

            print("Éxito. Respuesta de Supabase recibida")
            print(f"Usuario ID: {response.user.id if response.user else 'No ID'}")
            print(f"¿Tiene sesión?: {bool(response.session)}")

            access_token = response.session.access_token
            print("Éxito. Token de acceso obtenido")

            try:
                user_id = response.user.id
                now = datetime.now(timezone.utc).isoformat()
                supabase.table("usuarios").update({"ultimo_acceso": now}).eq("id", user_id).execute()
                print(f"Éxito. Actualizado último acceso para usuario {user_id}")
            except Exception as e:
                print(f"Advertencia: Error al actualizar último acceso: {str(e)}")

            return {
                "access_token": access_token,
                "token_type": "bearer"
            }
        except Exception as supabase_error:
            print(f"Error en Supabase Auth: {supabase_error}")
            print(f"Tipo de error: {type(supabase_error)}")

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
        print(f"Error general en login: {e}")
        print(f"Tipo de error: {type(e)}")
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
        print(f"Datos de registro recibidos: {user_data.dict()}")

        # En la nueva lógica, siempre se crea un negocio nuevo automáticamente
        # Los usuarios serán invitados por administradores de negocio en el futuro

        # Usar cliente anónimo para el registro para que auth.uid() sea null
        supabase = get_supabase_anon_client()

        print("Registrando usuario en Supabase Auth...")
        
        # En modo desarrollo, deshabilitar confirmación de email
        signup_options = {
            "email": user_data.email,
            "password": user_data.password,
        }
        
        # Solo en modo DEBUG, deshabilitar confirmación de email
        if settings.DEBUG:
            print("🔧 MODO DEBUG: Deshabilitando confirmación de email")
            signup_options["options"] = {
                "email_confirm": False  # Deshabilitar confirmación en desarrollo
            }
        
        auth_response = supabase.auth.sign_up(signup_options)

        if not auth_response.user or not auth_response.user.id:
            raise Exception("Error al crear usuario en Supabase Auth - no se obtuvo ID de usuario")

        user_id = auth_response.user.id
        print(f"Usuario creado en Supabase Auth con ID: {user_id}")

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
        print(f"Perfil creado en tabla usuarios: {response.data}")

        # Registro simple: el usuario se registra sin negocio automático
        # Podrá crear un negocio manualmente o ser invitado a uno existente
        print(f"Usuario {user_data.email} registrado exitosamente. Puede crear un negocio o ser invitado a uno existente.")

        # Mensaje diferente según el modo
        if settings.DEBUG:
            message = "Usuario registrado correctamente. En modo desarrollo, no se requiere confirmación de email."
            requires_confirmation = False
        else:
            message = "Usuario registrado correctamente. Por favor revisa tu email para confirmar la cuenta antes de iniciar sesión."
            requires_confirmation = True

        print("✅ Usuario registrado exitosamente.")
        return SignUpResponse(
            message=message,
            email=user_data.email,
            requires_confirmation=requires_confirmation
        )

    except Exception as e:
        print(f"Registration error: {str(e)}")
        print(traceback.format_exc())
        exc_type, exc_obj, exc_tb = sys.exc_info()
        print(f"Excepción en línea {exc_tb.tb_lineno}")
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
    """
    Get current user
    """
    try:
        if not hasattr(request.state, 'user') or not request.state.user:
            raise HTTPException(status_code=401, detail="Usuario no autenticado")
        
        user = request.state.user
        user_id = user.id
        
        # Obtener información del usuario desde la tabla usuarios
        supabase = get_supabase_client()
        
        response = supabase.table("usuarios").select("*").eq("id", user_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        user_data = response.data[0]
        
        # Agregar información adicional del auth de Supabase
        user_data.update({
            "email": user.email,
            "email_confirmed_at": user.email_confirmed_at,
            "last_sign_in_at": user.last_sign_in_at,
        })
        
        return user_data
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error al obtener información del usuario: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.put("/profile", response_model=dict)
async def update_profile(profile_data: dict, request: Request) -> Any:
    """
    Update current user's profile information
    """
    try:
        if not hasattr(request.state, 'user') or not request.state.user:
            raise HTTPException(status_code=401, detail="Usuario no autenticado")
        
        user = request.state.user
        user_id = user.id
        
        # Validar que solo se actualicen campos permitidos
        allowed_fields = ['nombre', 'apellido', 'telefono']
        update_data = {k: v for k, v in profile_data.items() if k in allowed_fields and v is not None}
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No hay datos válidos para actualizar")
        
        # Agregar timestamp de actualización
        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        
        # Actualizar en la base de datos
        supabase = get_supabase_client()
        response = supabase.table("usuarios").update(update_data).eq("id", user_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        updated_user = response.data[0]
        
        # Agregar información adicional del auth de Supabase
        updated_user.update({
            "email": user.email,
            "email_confirmed_at": user.email_confirmed_at,
            "last_sign_in_at": user.last_sign_in_at,
        })
        
        return updated_user
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error al actualizar perfil: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.put("/change-password", response_model=dict)
async def change_password(password_data: dict, request: Request) -> Any:
    """
    Change current user's password
    """
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
        
        # Verificar contraseña actual intentando hacer login
        supabase = get_supabase_client()
        
        try:
            # Intentar iniciar sesión con las credenciales actuales para verificar la contraseña
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
        
        # Actualizar la contraseña usando Supabase Auth
        try:
            # Obtener el token actual del request
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            
            # Usar el token para actualizar la contraseña
            supabase.auth.update_user(
                token,
                {"password": new_password}
            )
            
            return {"message": "Contraseña actualizada correctamente"}
            
        except Exception as update_error:
            print(f"Error al actualizar contraseña: {str(update_error)}")
            raise HTTPException(status_code=500, detail="Error al actualizar la contraseña")
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error general al cambiar contraseña: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/activate/{email}")
async def activate_user(email: str) -> Any:
    """
    SOLO PARA DESARROLLO: Activa la cuenta de un usuario sin necesidad de confirmar email
    En producción, esta ruta debe ser eliminada o protegida
    """
    try:
        # Esta ruta solo debe estar disponible en entorno de desarrollo
        if not settings.DEBUG:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Esta función solo está disponible en entorno de desarrollo"
            )
            
        supabase = get_supabase_client()
        
        # Buscar usuario por email
        user_data = supabase.table("usuarios").select("id").eq("email", email).execute()
        
        if not user_data.data or len(user_data.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Usuario con email {email} no encontrado"
            )
            
        user_id = user_data.data[0]["id"]
        
        # Intentar actualizar el usuario usando la API admin
        try:
            # Usar el service role key para operaciones admin
            admin_supabase = get_supabase_client()  # Ya usa service role
            
            # Actualizar el usuario para marcarlo como confirmado
            # Esto requiere usar la API REST directamente
            
            headers = {
                "Authorization": f"Bearer {settings.SUPABASE_KEY}",
                "Content-Type": "application/json",
                "apikey": settings.SUPABASE_KEY
            }
            
            # Actualizar usuario via API admin
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
                print(f"Error en API admin: {response.status_code} - {response.text}")
                
                # Fallback: marcar como confirmado en nuestra tabla
                now = datetime.now(timezone.utc).isoformat()
                supabase.table("usuarios").update({
                    "email_confirmado": True,
                    "email_confirmado_en": now
                }).eq("id", user_id).execute()
                
                return {
                    "detail": f"Usuario {email} marcado como confirmado en base de datos local",
                    "user_id": user_id,
                    "status": "confirmed_locally",
                    "note": "Para confirmación completa, ve a Supabase Dashboard > Authentication > Users y marca como confirmado"
                }
                
        except Exception as admin_error:
            print(f"Error en activación admin: {str(admin_error)}")
            
            # Fallback: dar instrucciones manuales
            return {
                "detail": "No se pudo activar automáticamente",
                "user_id": user_id,
                "email": email,
                "instrucciones": [
                    "1. Ve a Supabase Dashboard: https://supabase.com/dashboard",
                    "2. Selecciona tu proyecto",
                    "3. Ve a Authentication > Users",
                    f"4. Busca el usuario {email}",
                    "5. Haz clic en el usuario y marca 'Email Confirmed' como true",
                    "ALTERNATIVA: Deshabilita 'Confirm Email' en Authentication > Settings"
                ]
            }
        
    except Exception as e:
        print(f"Error en activate_user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al activar usuario: {str(e)}"
        )


@router.get("/confirm")
async def confirm_redirect():
    """
    Redirige las solicitudes de confirmación al frontend
    Esta ruta captura todas las solicitudes de confirmación de Supabase y las redirige
    a nuestra aplicación frontend en el puerto correcto.
    """
    # Redirigir al endpoint de confirmación en el frontend
    return RedirectResponse(url=settings.FRONTEND_CONFIRMATION_URL)


@router.get("/check-confirmation/{email}")
async def check_email_confirmation(email: str) -> Any:
    """
    Verificar si un email ha sido confirmado
    """
    try:
        supabase = get_supabase_client()
        
        # Buscar usuario en la tabla usuarios
        user_response = supabase.table("usuarios").select("id, email").eq("email", email).execute()
        
        if not user_response.data or len(user_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )
        
        # Intentar hacer login para verificar si el email está confirmado
        # Si el email no está confirmado, Supabase dará error
        try:
            # Usamos una contraseña temporal para verificar el estado
            # El error nos dirá si es por email no confirmado o credenciales inválidas
            test_response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": "test_password_for_verification"
            })
            
            # Si llegamos aquí, significa que las credenciales son válidas
            # pero esto no debería pasar con una contraseña de prueba
            return {
                "email": email,
                "is_confirmed": True,
                "message": "Email confirmado"
            }
            
        except Exception as auth_error:
            error_message = str(auth_error)
            
            if "Email not confirmed" in error_message:
                return {
                    "email": email,
                    "is_confirmed": False,
                    "message": "Email no confirmado. Por favor revisa tu correo electrónico."
                }
            elif "Invalid login credentials" in error_message:
                # Si el error es de credenciales inválidas, significa que el email SÍ está confirmado
                # pero la contraseña de prueba es incorrecta (que es lo esperado)
                return {
                    "email": email,
                    "is_confirmed": True,
                    "message": "Email confirmado"
                }
            else:
                # Otro tipo de error
                return {
                    "email": email,
                    "is_confirmed": False,
                    "message": f"Error al verificar confirmación: {error_message}"
                }
                
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error al verificar confirmación de email: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )


@router.post("/resend-confirmation")
async def resend_confirmation_email(email_data: dict) -> Any:
    """
    Reenviar email de confirmación
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
            resend_response = supabase.auth.resend({
                "type": "signup",
                "email": email
            })
            
            return {
                "message": "Email de confirmación reenviado correctamente",
                "email": email
            }
            
        except Exception as resend_error:
            error_message = str(resend_error)
            
            if "Email already confirmed" in error_message:
                return {
                    "message": "El email ya está confirmado",
                    "email": email,
                    "already_confirmed": True
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Error al reenviar confirmación: {error_message}"
                )
                
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error al reenviar confirmación: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )


@router.delete("/users/{user_id}")
async def delete_user_completely(user_id: str, request: Request) -> Any:
    """Eliminar usuario completamente con todos sus datos relacionados."""
    try:
        print(f"=== Iniciando eliminación completa del usuario {user_id} ===")
        
        # Verificar que el usuario autenticado puede eliminar este usuario
        current_user = getattr(request.state, "user", None)
        if not current_user:
            raise HTTPException(status_code=401, detail="Usuario no autenticado")
        
        # Solo permitir que el usuario se elimine a sí mismo o que sea un admin
        if current_user.id != user_id:
            # Verificar si es admin de algún negocio donde el usuario a eliminar es empleado
            supabase = get_supabase_client()
            admin_check = supabase.table("usuarios_negocios") \
                .select("negocio_id") \
                .eq("usuario_id", current_user.id) \
                .eq("rol", "admin") \
                .eq("estado", "aceptado") \
                .execute()
            
            if not admin_check.data:
                raise HTTPException(status_code=403, detail="No tienes permisos para eliminar este usuario")
            
            # Verificar que el usuario a eliminar está en alguno de los negocios del admin
            admin_business_ids = [item["negocio_id"] for item in admin_check.data]
            user_in_business = supabase.table("usuarios_negocios") \
                .select("negocio_id") \
                .eq("usuario_id", user_id) \
                .in_("negocio_id", admin_business_ids) \
                .execute()
            
            if not user_in_business.data:
                raise HTTPException(status_code=403, detail="No puedes eliminar este usuario")
        
        # Verificar que el usuario existe
        user_check = supabase.table("usuarios") \
            .select("id, email, nombre, apellido") \
            .eq("id", user_id) \
            .execute()
        
        if not user_check.data:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        user_data = user_check.data[0]
        print(f"Eliminando usuario: {user_data['email']} ({user_data['nombre']} {user_data['apellido']})")
        
        # La eliminación en cascada se manejará automáticamente por los triggers
        # Solo necesitamos eliminar el registro principal de usuarios
        delete_response = supabase.table("usuarios") \
            .delete() \
            .eq("id", user_id) \
            .execute()
        
        if hasattr(delete_response, 'error') and delete_response.error:
            print(f"❌ Error eliminando usuario: {delete_response.error}")
            raise HTTPException(status_code=500, detail=f"Error eliminando usuario: {delete_response.error}")
        
        print(f"✅ Usuario {user_data['email']} eliminado completamente")
        
        return {
            "message": "Usuario eliminado completamente",
            "user_id": user_id,
            "email": user_data['email'],
            "deleted_data": [
                "Usuario de la tabla usuarios",
                "Usuario de auth.users", 
                "Relaciones usuario-negocio",
                "Permisos del usuario",
                "Negocios creados por el usuario (si los había)",
                "Todos los datos relacionados"
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error inesperado eliminando usuario: {type(e).__name__} - {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno eliminando usuario: {str(e)}"
        )


@router.delete("/users/by-email/{email}")
async def delete_user_by_email(email: str, request: Request) -> Any:
    """Eliminar usuario por email (útil para desarrollo y testing)."""
    try:
        print(f"=== Buscando usuario por email: {email} ===")
        
        supabase = get_supabase_client()
        
        # Buscar usuario por email
        user_check = supabase.table("usuarios") \
            .select("id, email, nombre, apellido") \
            .eq("email", email) \
            .execute()
        
        if not user_check.data:
            raise HTTPException(status_code=404, detail=f"Usuario con email {email} no encontrado")
        
        user_data = user_check.data[0]
        user_id = user_data["id"]
        
        print(f"Usuario encontrado: {user_id}")
        
        # Simular request con el usuario encontrado para permitir auto-eliminación
        request.state.user = type('User', (), {'id': user_id})()
        
        # Verificar que el usuario existe
        print(f"Eliminando usuario: {user_data['email']} ({user_data['nombre']} {user_data['apellido']})")
        
        # 1. Eliminar de la tabla usuarios (esto activará los triggers de cascada)
        delete_response = supabase.table("usuarios") \
            .delete() \
            .eq("id", user_id) \
            .execute()
        
        if hasattr(delete_response, 'error') and delete_response.error:
            print(f"❌ Error eliminando usuario: {delete_response.error}")
            raise HTTPException(status_code=500, detail=f"Error eliminando usuario: {delete_response.error}")
        
        # 2. Eliminar de auth.users usando la API de administración
        auth_deleted = await supabase_admin.delete_auth_user(user_id)
        
        print(f"✅ Usuario {user_data['email']} eliminado completamente")
        
        return {
            "message": "Usuario eliminado completamente",
            "user_id": user_id,
            "email": user_data['email'],
            "deleted_data": [
                "Usuario de la tabla usuarios",
                "Usuario de auth.users" if auth_deleted else "Usuario de auth.users (error)", 
                "Relaciones usuario-negocio",
                "Permisos del usuario",
                "Negocios creados por el usuario (si los había)",
                "Todos los datos relacionados"
            ],
            "auth_deletion_success": auth_deleted
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error eliminando usuario por email: {e}")
        raise HTTPException(status_code=500, detail=f"Error eliminando usuario: {str(e)}") 
