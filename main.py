from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys

from app.api.api_v1.api import api_router
from app.core.config import settings
from app.db.supabase_client import get_supabase_client, check_supabase_connection
from app.api.middleware.supabase_auth import SupabaseAuthMiddleware
from app.api.middleware.plan_limits import PlanLimitsMiddleware # Import PlanLimitsMiddleware

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# CORS configuration - allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permitir todos los orígenes en desarrollo
    allow_credentials=True,
    allow_methods=["*"],  # Permitir todos los métodos
    allow_headers=["*"],  # Permitir todos los headers
)

# Add SupabaseAuthMiddleware
# This middleware will process requests and make request.state.supabase_user available
app.add_middleware(SupabaseAuthMiddleware)

# Add PlanLimitsMiddleware (placeholder) - runs after SupabaseAuthMiddleware
# This middleware is currently a placeholder and will just log information.
app.add_middleware(PlanLimitsMiddleware)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    # Verificar y reportar el estado de la conexión a Supabase
    supabase_status = "Conectado" if check_supabase_connection() else "Error de conexión"
    return {
        "message": "Bienvenido a MicroPymes API",
        "status": {
            "supabase": supabase_status
        }
    }

@app.on_event("startup")
async def startup_event():
    # Verificar la conexión con Supabase al iniciar
    print("Verificando conexión con Supabase...")
    
    # Intentar inicializar el cliente
    try:
        client = get_supabase_client()
        print("Cliente Supabase inicializado correctamente")
        
        # Intentar verificar la conexión
        if check_supabase_connection():
            print("✅ Conexión con Supabase establecida correctamente")
        else:
            print("⚠️ No se pudo verificar la conexión con Supabase - verifica tus credenciales")
            print("⚠️ La aplicación requiere Supabase para funcionar")
            sys.exit(1)  # Finalizar la aplicación si no hay conexión con Supabase
    except Exception as e:
        print(f"❌ Error al inicializar Supabase: {str(e)}")
        print("❌ La aplicación requiere Supabase para funcionar. Asegúrate de que tu archivo .env contiene las credenciales correctas.")
        sys.exit(1)  # Finalizar la aplicación si hay error al inicializar Supabase 