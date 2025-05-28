from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import sys
import time
from typing import List, Optional
import os

from app.api.api_v1.api import api_router
from app.core.config import settings
from app.db.supabase_client import get_supabase_client, check_supabase_connection

# Get allowed origins from environment or use default
ALLOWED_ORIGINS: List[str] = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:3000"  # Default development origins
).split(",")

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

async def connect_to_supabase() -> bool:
    """Attempt to connect to Supabase with retries"""
    for attempt in range(MAX_RETRIES):
        try:
            client = get_supabase_client()
            if check_supabase_connection():
                print(f"✅ Conexión con Supabase establecida correctamente (intento {attempt + 1})")
                return True
        except Exception as e:
            print(f"⚠️ Intento {attempt + 1} fallido: {str(e)}")
            if attempt < MAX_RETRIES - 1:
                print(f"Reintentando en {RETRY_DELAY} segundos...")
                time.sleep(RETRY_DELAY)
    
    return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Verificando conexión con Supabase...")
    if not await connect_to_supabase():
        print("❌ No se pudo establecer conexión con Supabase después de varios intentos")
        print("❌ La aplicación requiere Supabase para funcionar")
        sys.exit(1)
    
    yield
    
    # Shutdown
    print("Cerrando aplicación...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# CORS configuration with specific origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

async def auth_middleware(request: Request, call_next):
    """Middleware to authenticate Supabase sessions."""
    if request.method == "OPTIONS":
        return await call_next(request)

    # Lista de rutas públicas que no requieren autenticación
    public_routes = [
        "/",
        "/api/v1/docs",
        "/api/v1/openapi.json",
        "/api/v1/auth/login",
        "/api/v1/auth/signup",
        "/api/v1/auth/confirm",
        "/api/v1/auth/activate"
    ]

    # Verificar si la ruta actual es pública
    is_public_route = any(request.url.path.startswith(route) for route in public_routes)

    token = request.headers.get("Authorization", "").replace("Bearer ", "")

    if not is_public_route:
        # Si la ruta no es pública, se requiere un token
        if not token:
            print("Authentication Middleware: Non-public route, no token provided, returning 401")
            return Response("Unauthorized: Missing token", status_code=401)

        try:
            supabase = get_supabase_client()
            print(f"Authentication Middleware: Non-public route, attempting to get user with token: {token[:10]}...") # Log first 10 chars of token
            auth_response = supabase.auth.get_user(token)
            
            print(f"Authentication Middleware: Raw Supabase get_user response type: {type(auth_response)}")
            print(f"Authentication Middleware: Raw Supabase get_user response: {auth_response}")

            user_from_auth = None
            # Supabase client <= 1.0 returns a tuple (user, error), > 1.0 returns an object with user/error attributes
            if isinstance(auth_response, tuple):
                 # Older client version
                 user_from_auth, error = auth_response
                 if error:
                     print(f"Authentication Middleware: Supabase error in tuple response: {error}")
            elif hasattr(auth_response, 'user') and auth_response.user:
                 # Newer client version
                 user_from_auth = auth_response.user

            print(f"Authentication Middleware: Extracted user from response: {user_from_auth}")
            
            if user_from_auth:
                request.state.user = user_from_auth
                print(f"Authentication Middleware: User {user_from_auth.id} attached to request.state")
            else:
                print("Authentication Middleware: Non-public route, get_user did not return a valid user object, returning 401")
                return Response("Unauthorized: Invalid token or no user found", status_code=401)

        except Exception as e:
            # Log the exception for debugging
            print(f"Authentication Middleware: Exception during get_user call on non-public route: {type(e).__name__} - {e}")
            return Response(f"Unauthorized: Authentication error: {e}", status_code=401)

    elif token: # is_public_route is True
        # If it's a public route but a token is provided, still try to attach the user for convenience
        try:
            supabase = get_supabase_client()
            print(f"Authentication Middleware: Public route with token, attempting to get user: {token[:10]}...")
            auth_response = supabase.auth.get_user(token)

            user_from_auth = None
            if isinstance(auth_response, tuple):
                 user_from_auth, error = auth_response
            elif hasattr(auth_response, 'user') and auth_response.user:
                 user_from_auth = auth_response.user
                 
            if user_from_auth:
                 request.state.user = user_from_auth
                 print(f"Authentication Middleware: User {user_from_auth.id} attached to request.state on public route")
            # else: no error needed, public route

        except Exception as e:
            print(f"Authentication Middleware: Exception during get_user call on public route: {type(e).__name__} - {e}")
            # No need to return 401, it's a public route

    # If it's a public route without a token, or if the token validation passed/failed gracefully,
    # continue to the next middleware/endpoint.
    print(f"Authentication Middleware: Proceeding to next middleware/endpoint for {request.url.path}")
    response = await call_next(request)
    return response

app.middleware("http")(auth_middleware)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root() -> dict:
    try:
        supabase_status = "Conectado" if check_supabase_connection() else "Error de conexión"
        return {
            "message": "Bienvenido a MicroPymes API",
            "status": {
                "supabase": supabase_status,
                "version": settings.VERSION,
                "environment": settings.ENVIRONMENT
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al verificar el estado del sistema: {str(e)}"
        ) 