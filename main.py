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

# CONFIGURACIÓN DE LOGS
configure_logging()
logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

async def connect_to_supabase() -> bool:
    """Attempt to connect to Supabase with retries"""
    for attempt in range(MAX_RETRIES):
        try:
            client = get_supabase_client()
            if check_supabase_connection():
                logger.info("[supabase] Connection established on attempt %s", attempt + 1)
                return True
        except Exception as e:
            logger.warning("[supabase] Attempt %s failed: %s", attempt + 1, e)
            if attempt < MAX_RETRIES - 1:
                logger.info("[supabase] Retrying connection in %s seconds", RETRY_DELAY)
                await asyncio.sleep(RETRY_DELAY)
    return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Checking Supabase connectivity on startup")
    if not await connect_to_supabase():
        logger.error("Unable to establish Supabase connection after %s attempts", MAX_RETRIES)
        # No salimos (sys.exit) para permitir que la app arranque y devuelva errores 500 controlados
        # en lugar de crashear el contenedor completo.
    
    yield
    
    # Shutdown
    logger.info("Shutting down MicroPymes API")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# 1. PRIMERO: CORS (Debe ser el middleware más externo para manejar headers incluso en errores)
# Usamos settings.BACKEND_CORS_ORIGINS que ya procesa correctamente la variable de entorno
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS, 
    allow_credentials=True,
    allow_methods=["*"], # Permitir todos los métodos para evitar bloqueos de preflight
    allow_headers=["*"], # Permitir todos los headers
)

# 2. SEGUNDO: Middleware de Timeout (para evitar 502 de Render por esperas eternas)
@app.middleware("http")
async def timeout_middleware(request: Request, call_next):
    try:
        # Aumentamos a 45s para dar margen antes del timeout de Render (típicamente 60s)
        return await asyncio.wait_for(call_next(request), timeout=45.0)
    except asyncio.TimeoutError:
        logger.warning("Request timeout for %s", request.url.path)
        return JSONResponse(
            status_code=504,
            content={"detail": "Request processing timed out"}
        )
    except Exception as e:
        # Dejar pasar otras excepciones para que las maneje el error handler
        raise e

# 3. TERCERO: Error Handling
app.add_middleware(JSONErrorMiddleware)

# 4. CUARTO: Auth Middleware (Lógica de negocio)
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

    # Rutas públicas
    public_routes = [
        "/", "/health", "/wake-up", "/docs", "/redoc", "/openapi.json",
        f"{settings.API_V1_STR}/docs",
        f"{settings.API_V1_STR}/openapi.json",
        f"{settings.API_V1_STR}/auth/login",
        f"{settings.API_V1_STR}/auth/signup",
        f"{settings.API_V1_STR}/auth/confirm",
    ]
    
    if any(request.url.path.startswith(route) for route in public_routes):
        return await call_next(request)

    # Lógica simple de validación de token para rutas protegidas
    # (La validación profunda se hace en las dependencias de los endpoints)
    return await call_next(request)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root() -> dict:
    return {
        "message": "MicroPymes API",
        "version": settings.VERSION,
        "status": "OK",
        "cors_origins": settings.BACKEND_CORS_ORIGINS # Para depuración
    }

@app.get("/health")
async def health_check() -> dict:
    return {"status": "OK"}

@app.get("/wake-up")
async def wake_up() -> dict:
    return {"status": "awake"}
