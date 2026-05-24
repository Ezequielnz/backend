from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import logging

from app.api.api_v1.api import api_router
from app.core.config import settings
from app.core.logging_config import configure_logging
from app.db.local_db import check_db_connection
from app.middleware.error_handlers import JSONErrorMiddleware

# CONFIGURACIÓN DE LOGS
configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — verificar DB local
    logger.info("[startup] Verificando base de datos SQLite...")
    if check_db_connection():
        logger.info("[startup] ✅ Base de datos SQLite lista.")
    else:
        logger.error("[startup] ❌ No se pudo conectar a la base de datos SQLite.")

    yield

    # Shutdown
    logger.info("[shutdown] MicroPymes API detenido.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# 1. CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Timeout middleware
@app.middleware("http")
async def timeout_middleware(request: Request, call_next):
    try:
        return await asyncio.wait_for(call_next(request), timeout=45.0)
    except asyncio.TimeoutError:
        logger.warning("Request timeout: %s", request.url.path)
        return JSONResponse(
            status_code=504,
            content={"detail": "Request processing timed out"},
        )

# 3. Error handling
app.add_middleware(JSONErrorMiddleware)

# 4. Routers
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
async def root() -> dict:
    return {
        "message": "MicroPymes API",
        "version": settings.VERSION,
        "mode": "desktop",
        "status": "OK",
    }


@app.get("/health")
async def health_check() -> dict:
    db_ok = check_db_connection()
    return {"status": "OK" if db_ok else "DEGRADED", "db": "sqlite", "db_ok": db_ok}


@app.get("/wake-up")
async def wake_up() -> dict:
    return {"status": "awake"}
