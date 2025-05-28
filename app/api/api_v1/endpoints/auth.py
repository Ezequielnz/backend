from typing import Any
import uuid
import json
import time
import traceback
import sys
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import EmailStr, ValidationError
import jwt

from app.db.supabase_client import get_supabase_client
from app.core.config import settings
from app.types.auth import Token, UserLogin, UserSignUp

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
async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    try:
        # Iniciar sesión con Supabase
        supabase = get_supabase_client()
        
        print(f"Intentando iniciar sesión con Supabase: {form_data.username}")
        # Use Supabase Auth to sign in the user
        response = supabase.auth.sign_in_with_password({
            "email": form_data.username,
            "password": form_data.password,
        })
        
        access_token = response.session.access_token
        print("✅ Inicio de sesión exitoso con Supabase")
        
        # Actualizar último acceso del usuario
        try:
            user_id = response.user.id
            now = datetime.now(timezone.utc).isoformat()
            
            # Actualizar campo ultimo_acceso
            supabase.table("usuarios").update({"ultimo_acceso": now}).eq("id", user_id).execute()
            print(f"Actualizado último acceso para usuario {user_id}")
        except Exception as e:
            print(f"Error al actualizar último acceso: {str(e)}")
        
        return {
            "access_token": access_token,
            "token_type": "bearer"
        }
    except Exception as e:
        print(f"Login error: {str(e)}")
        
        # Mejorar el mensaje de error para "Email not confirmed"
        error_message = str(e)
        if "Email not confirmed" in error_message:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email no confirmado. Por favor revisa tu correo electrónico para activar tu cuenta.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Error al iniciar sesión: {error_message}",
            headers={"WWW-Authenticate": "Bearer"},
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


@router.post("/signup")
async def signup(user_data: UserSignUp) -> Any:
    """
    Create new user with the given data
    """
    try:
        print(f"Datos de registro recibidos: {user_data.dict()}")
        
        # Registrar con Supabase
        supabase = get_supabase_client()
        
        print("Registrando usuario en Supabase Auth...")
        # Registrar el usuario con Supabase Auth
        auth_response = supabase.auth.sign_up({
            "email": user_data.email,
            "password": user_data.password,
        })
        
        if not auth_response.user or not auth_response.user.id:
            raise Exception("Error al crear usuario en Supabase Auth - no se obtuvo ID de usuario")
        
        user_id = auth_response.user.id
        print(f"Usuario creado en Supabase Auth con ID: {user_id}")
        
        # Obtener timestamp actual en formato ISO para PostgreSQL
        now = datetime.now(timezone.utc).isoformat()
        
        # Crear perfil de usuario en la tabla 'usuarios'
        print("Creando perfil de usuario en tabla usuarios...")
        user_profile = {
            "id": user_id,
            "email": user_data.email,
            "nombre": user_data.nombre,
            "apellido": user_data.apellido,
            "creado_en": now,
            "ultimo_acceso": now
        }
        
        # Insertar perfil en Supabase
        response = supabase.table("usuarios").insert(user_profile).execute()
        print(f"Perfil creado en tabla usuarios: {response.data}")
        
        # Iniciar sesión inmediatamente después del registro para obtener un token
        print("Iniciando sesión para obtener token de acceso...")
        login_response = supabase.auth.sign_in_with_password({
            "email": user_data.email,
            "password": user_data.password,
        })
        
        if not login_response or not login_response.session:
            # Si no podemos obtener un token, aún así el registro fue exitoso
            # Devolvemos un mensaje indicando que el usuario debe confirmar su email
            return {
                "detail": "Usuario registrado correctamente. Por favor revisa tu email para confirmar la cuenta.",
                "user_id": user_id
            }
        
        # Retornar token de autenticación si el inicio de sesión fue exitoso
        return {
            "access_token": login_response.session.access_token,
            "token_type": "bearer"
        }
    except Exception as e:
        print(f"Registration error: {str(e)}")
        print(traceback.format_exc())
        exc_type, exc_obj, exc_tb = sys.exc_info()
        print(f"Excepción en línea {exc_tb.tb_lineno}")
        # Handle potential errors
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al crear usuario: {str(e)}",
        )


@router.get("/me", response_model=dict)
async def read_users_me(token: str = Depends(oauth2_scheme)) -> Any:
    """
    Get current user info
    """
    try:
        supabase = get_supabase_client()
        
        # Obtener información del usuario con el token
        response = supabase.auth.get_user(token)
        
        if not response.user:
            raise Exception("Usuario no encontrado en Supabase")
        
        # Obtener información adicional del usuario de la tabla usuarios
        user_id = response.user.id
        user_info_response = supabase.table("usuarios").select("*").eq("id", user_id).execute()
        
        if not user_info_response.data or len(user_info_response.data) == 0:
            return {"email": response.user.email}
        
        return user_info_response.data[0]
    except Exception as e:
        print(f"Get user error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Error de autenticación: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


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
            
        # Llamar API admin para configurar usuario como confirmado
        # (Esto requiere permisos de administrador en Supabase)
        try:
            # Debido a las limitaciones de la API de Supabase, no podemos confirmar directamente
            # Pero lo intentamos de todos modos
            admin_client = supabase.auth.admin
            admin_client.update_user_by_email(email, {"email_confirm": True})
            
            return {"detail": f"Usuario {email} activado exitosamente"}
        except Exception as admin_error:
            print(f"No se pudo activar mediante API admin: {str(admin_error)}")
            
            # Alternativa: dar instrucciones para activar manualmente
            return {
                "detail": "No se pudo activar automáticamente",
                "instrucciones": "Para activar la cuenta, ve a Supabase Dashboard > Authentication > Users y edita el usuario para marcarlo como confirmado"
            }
        
    except Exception as e:
        print(f"Error al activar usuario: {str(e)}")
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
    return RedirectResponse(url="http://localhost:5173/confirm-email") 