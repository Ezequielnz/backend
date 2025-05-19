from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.api.api_v1.api import api_router
from app.core.config import settings
from app.db.session import get_db
from app.db.init_db import init_db, init_db_with_data

# Inicializar la base de datos
init_db()

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Set all CORS enabled origins
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    return {"message": "Bienvenido a MicroPymes API"}

@app.on_event("startup")
async def startup_event():
    db = next(get_db())
    try:
        init_db_with_data(db)
    finally:
        db.close() 