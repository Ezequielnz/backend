from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import sys
import time
import asyncio
from typing import List, Optional
import os
import logging

from app.api.api_v1.api import api_router
from app.core.config import settings
from app.core.logging_config import configure_logging
from app.db.supabase_client import get_supabase_client, check_supabase_connection
from app.middleware.error_handlers import JSONErrorMiddleware

# CORRECCIÓN: Eliminamos la lectura manual de ALLOWED_ORIGINS.
# Usaremos settings.BACKEND_CORS_ORIGINS que ya procesa correctamente 
# la variable de entorno (JSON, espacios, comas, etc.) gracias a Pydantic.

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

configure_logging()
logger = logging.getLogger(__name__)

class SafeProtocolMiddleware:
    """ASGI middleware to gracefully handle h11 LocalProtocolError and client disconnections"""
    
    def __init__(self, app):
        self.app = app
        self.logger = logging.getLogger(__name__)
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        async def safe_send(message):
            try:
                await send(message)
            except Exception as e:
                error_type = str(type(e))
                error_msg = str(e)
                
                # Catch h11 protocol errors and client disconnections
                if (
                    "LocalProtocolError" in error_type
                    or "RemoteProtocolError" in error_type
                    or "ClientDisconnect" in error_type
                    or "Can't send data when our state is ERROR" in error_msg
                    or "Connection lost" in error_msg
                ):
                    self.logger.debug(f"Protocol error swallowed: {error_type} - {error_msg}")
                    # Silently ignore - client already disconnected
                    return
                else:
                    # Re-raise other exceptions
                    self.logger.error(f"Unexpected ASGI send error: {error_type} - {error_msg}")
                    raise
        
        try:
            await self.app(scope, receive, safe_send)
        except Exception as e:
            error_type = str(type(e))
            error_msg = str(e)
            
            # Additional safety net for any protocol errors that bubble up
            if (
                "LocalProtocolError" in error_type
                or "RemoteProtocolError" in error_type
                or "ClientDisconnect" in error_type
                or "Can't send data" in error_msg
            ):
                self.logger.debug(f"ASGI protocol error swallowed: {error_type} - {error_msg}")
                return
            else:
                # Re-raise other exceptions
                raise

async def connect_to_supabase() -> bool:
    """Attempt to connect to Supabase with retries"""
    for attempt in range(MAX_RETRIES):
        try:
            client = get_supabase_client()
            if check_supabase_connection():
                logger.info(
                    "[supabase] Connection established on attempt %s", attempt + 1
                )
                return True
        except Exception as e:
            logger.warning("[supabase] Attempt %s failed: %s", attempt + 1, e)
            if attempt < MAX_RETRIES - 1:
                logger.info(
                    "[supabase] Retrying connection in %s seconds", RETRY_DELAY
                )
                await asyncio.sleep(RETRY_DELAY)
    
    return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Checking Supabase connectivity on startup")
    if not await connect_to_supabase():
        logger.error(
            "Unable to establish Supabase connection after %s attempts", MAX_RETRIES
        )
        logger.error("The application cannot start without Supabase connectivity")
        sys.exit(1)
    
    yield
    
    # Shutdown
    logger.info("Shutting down MicroPymes API")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Agregar middleware para errores JSON en rutas API
app.add_middleware(JSONErrorMiddleware)

async def auth_middleware(request: Request, call_next):
    """Middleware to authenticate Supabase sessions."""
    try:
        if request.method == "OPTIONS":
            return await call_next(request)

        # Lista de rutas públicas que no requieren autenticación
        public_routes = [
            "/",
            "/health",
            "/wake-up",
            "/api/v1/docs",
            "/api/v1/openapi.json",
            "/api/v1/auth/login",
            "/api/v1/auth/signup",
            "/api/v1/auth/confirm",
            "/api/v1/auth/activate",
            "/test-products",
            "/test-services", 
            "/test-businesses"
        ]

        # Verificar si la ruta actual es pública
        is_public_route = any(request.url.path.startswith(route) for route in public_routes)
        
        # Temporary: make ONLY business products/services GET routes public for testing
        # This allows access to products and services endpoints without authentication during development
        if (request.method == "GET" and 
            "/businesses/" in request.url.path and 
            ("/products" in request.url.path or "/services" in request.url.path)):
            is_public_route = True
            logger.debug("Making business route public: %s", request.url.path)
        
        logger.debug("Path %s, is_public_route=%s", request.url.path, is_public_route)

        token = request.headers.get("Authorization", "").replace("Bearer ", "")

        if not is_public_route:
            # Si la ruta no es pública, se requiere un token
            if not token:
                logger.warning(
                    "Authentication Middleware: Non-public route without token for %s",
                    request.url.path,
                )
                # Usar JSONResponse para rutas de API
                if "/api/" in request.url.path:
                    return JSONResponse(
                        status_code=401,
                        content={
                            "detail": "Unauthorized: Missing token",
                            "error": "UNAUTHORIZED"
                        }
                    )
                else:
                    return Response(
                        content="Unauthorized: Missing token",
                        status_code=401,
                        headers={"Content-Type": "text/plain"}
                    )

            try:
                supabase = get_supabase_client()
                logger.debug(
                    "Authentication Middleware: Validating token for %s (prefix=%s...)",
                    request.url.path,
                    token[:10],
                )
                auth_response = supabase.auth.get_user(token)
                
                user_from_auth = None
                # Supabase client <= 1.0 returns a tuple (user, error), > 1.0 returns an object with user/error attributes
                if isinstance(auth_response, tuple):
                     # Older client version
                     user_from_auth, error = auth_response
                     if error:
                         logger.error("Authentication Middleware: Supabase error: %s", error)
                elif auth_response is not None and hasattr(auth_response, 'user') and auth_response.user:
                     # Newer client version
                     user_from_auth = auth_response.user

                if user_from_auth:
                    request.state.user = user_from_auth
                    logger.debug(
                        "Authentication Middleware: User %s attached to request.state",
                        user_from_auth.id,
                    )
                else:
                    logger.warning(
                        "Authentication Middleware: Invalid user/token combination for %s",
                        request.url.path,
                    )
                    # Usar JSONResponse para rutas de API
                    if "/api/" in request.url.path:
                        return JSONResponse(
                            status_code=401,
                            content={
                                "detail": "Unauthorized: Invalid token or no user found",
                                "error": "UNAUTHORIZED"
                            }
                        )
                    else:
                        return Response(
                            content="Unauthorized: Invalid token or no user found",
                            status_code=401,
                            headers={"Content-Type": "text/plain"}
                        )

            except Exception as e:
                # Log the exception for debugging
                logger.error(
                    "Authentication Middleware: Exception validating token for %s: %s - %s",
                    request.url.path,
                    type(e).__name__,
                    e,
                )
                # Usar JSONResponse para rutas de API
                if "/api/" in request.url.path:
                    return JSONResponse(
                        status_code=401,
                        content={
                            "detail": "Unauthorized: Authentication error",
                            "error": "UNAUTHORIZED",
                            "message": str(e)
                        }
                    )
                else:
                    return Response(
                        content=f"Unauthorized: Authentication error",
                        status_code=401,
                        headers={"Content-Type": "text/plain"}
                    )

        elif token: # is_public_route is True
            # If it's a public route but a token is provided, still try to attach the user for convenience
            try:
                supabase = get_supabase_client()
                logger.debug(
                    "Authentication Middleware: Public route token detected for %s (prefix=%s...)",
                    request.url.path,
                    token[:10],
                )
                auth_response = supabase.auth.get_user(token)

                user_from_auth = None
                if isinstance(auth_response, tuple):
                     user_from_auth, error = auth_response
                elif auth_response is not None and hasattr(auth_response, 'user') and auth_response.user:
                     user_from_auth = auth_response.user
                     
                if user_from_auth:
                     request.state.user = user_from_auth
                     logger.debug(
                         "Authentication Middleware: User %s attached on public route",
                         user_from_auth.id,
                     )
                # else: no error needed, public route

            except Exception as e:
                logger.error(
                    "Authentication Middleware: Public route token exception for %s: %s - %s",
                    request.url.path,
                    type(e).__name__,
                    e,
                )
                # No need to return 401, it's a public route

        # If it's a public route without a token, or if the token validation passed/failed gracefully,
        # continue to the next middleware/endpoint.
        logger.debug(
            "Authentication Middleware: Proceeding to next handler for %s",
            request.url.path,
        )
        response = await call_next(request)
        return response
        
    except Exception as e:
        logger.error(
            "Authentication Middleware: Critical error on %s: %s - %s",
            request.url.path,
            type(e).__name__,
            e,
        )
        # Usar JSONResponse para rutas de API
        if "/api/" in request.url.path:
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "error": "INTERNAL_SERVER_ERROR",
                    "message": str(e)
                }
            )
        else:
            return Response(
                content="Internal server error",
                status_code=500,
                headers={"Content-Type": "text/plain"}
        )

app.middleware("http")(auth_middleware)

# JSON Error middleware ya está registrado arriba

# Timeout middleware para evitar que las requests se cuelguen
async def timeout_middleware(request: Request, call_next):
    """Middleware to handle request timeouts"""
    try:
        # Timeout de 30 segundos para evitar requests muy largas
        response = await asyncio.wait_for(call_next(request), timeout=30.0)
        return response
    except asyncio.TimeoutError:
        logger.warning("Request timeout for %s", request.url.path)
        return Response("Request timeout", status_code=408)
    except asyncio.CancelledError:
        # Client disconnected; avoid sending a response body
        logger.info("Request cancelled (client disconnected) for %s", request.url.path)
        return Response(status_code=204)
    except ConnectionError as e:
        logger.warning("Connection error for %s: %s", request.url.path, e)
        return Response("Connection error", status_code=503)
    except Exception as e:
        logger.error("Timeout middleware error for %s: %s", request.url.path, e)
        return Response("Internal server error", status_code=500)

app.middleware("http")(timeout_middleware)

# CORS configuration using settings to ensure proper parsing
# CORRECCIÓN: Usar settings.BACKEND_CORS_ORIGINS en lugar de parseo manual
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS, 
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root() -> dict:
    """Endpoint raíz de la API - información básica del servicio."""
    try:
        return {
            "message": "Bienvenido a MicroPymes API",
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
            "status": "OK",
            "docs": f"{settings.API_V1_STR}/docs"
        }
    except Exception as e:
        return {
            "message": "MicroPymes API",
            "status": "Error", 
            "error": str(e)
        }

@app.get("/health")
async def health_check() -> dict:
    """Endpoint de verificación de salud del sistema."""
    try:
        supabase_status = "Conectado" if check_supabase_connection() else "Error de conexión"
        return {
            "status": "OK",
            "timestamp": time.time(),
            "services": {
                "supabase": supabase_status,
                "api": "OK"
            },
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
            # Usar la configuración unificada también en la respuesta de salud
            "allowed_origins": settings.BACKEND_CORS_ORIGINS
        }
    except Exception as e:
        return {
            "status": "Error",
            "timestamp": time.time(),
            "error": str(e),
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT
        }

@app.get("/wake-up")
async def wake_up() -> dict:
    """Endpoint para despertar el servicio en Render (evita cold starts)."""
    return {
        "status": "awake",
        "timestamp": time.time(),
        "message": "Servicio activo y listo para recibir requests"
    }

@app.get("/test-products/{business_id}")
async def test_products(business_id: str):
    """Test endpoint to check products without authentication"""
    try:
        supabase = get_supabase_client()
        response = supabase.table("productos").select("*").eq("negocio_id", business_id).execute()
        return {
            "status": "success",
            "business_id": business_id,
            "products": response.data if response.data else [],
            "count": len(response.data) if response.data else 0
        }
    except Exception as e:
        return {
            "status": "error",
            "business_id": business_id,
            "error": str(e)
        }

@app.get("/test-services/{business_id}")
async def test_services(business_id: str):
    """Test endpoint to check services without authentication"""
    try:
        supabase = get_supabase_client()
        response = supabase.table("servicios").select("*").eq("negocio_id", business_id).execute()
        return {
            "status": "success",
            "business_id": business_id,
            "services": response.data if response.data else [],
            "count": len(response.data) if response.data else 0
        }
    except Exception as e:
        return {
            "status": "error",
            "business_id": business_id,
            "error": str(e)
        }

@app.get("/test-businesses")
async def test_businesses():
    """Test endpoint to list businesses without authentication"""
    try:
        supabase = get_supabase_client()
        response = supabase.table("negocios").select("*").limit(5).execute()
        return {
            "status": "success",
            "businesses": response.data if response.data else [],
            "count": len(response.data) if response.data else 0
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

# Apply SafeProtocolMiddleware as the outermost layer to catch h11 errors
app = SafeProtocolMiddleware(app)
