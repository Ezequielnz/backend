from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import sys
import time
from typing import List
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