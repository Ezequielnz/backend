from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys

from app.api.api_v1.api import api_router
from app.core.config import settings
from app.db.supabase_client import get_supabase_client, check_supabase_connection

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Verificando conexión con Supabase...")
    try:
        client = get_supabase_client()
        print("Cliente Supabase inicializado correctamente")
        
        if not check_supabase_connection():
            print("⚠️ No se pudo verificar la conexión con Supabase - verifica tus credenciales")
            print("⚠️ La aplicación requiere Supabase para funcionar")
            sys.exit(1)
        print("✅ Conexión con Supabase establecida correctamente")
    except Exception as e:
        print(f"❌ Error al inicializar Supabase: {str(e)}")
        print("❌ La aplicación requiere Supabase para funcionar. Asegúrate de que tu archivo .env contiene las credenciales correctas.")
        sys.exit(1)
    
    yield
    
    # Shutdown
    print("Cerrando aplicación...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# CORS configuration - allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permitir todos los orígenes en desarrollo
    allow_credentials=True,
    allow_methods=["*"],  # Permitir todos los métodos
    allow_headers=["*"],  # Permitir todos los headers
)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root() -> dict:
    # Verificar y reportar el estado de la conexión a Supabase
    supabase_status = "Conectado" if check_supabase_connection() else "Error de conexión"
    return {
        "message": "Bienvenido a MicroPymes API",
        "status": {
            "supabase": supabase_status
        }
    } 