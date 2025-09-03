import os
import json
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "MicroPymes"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")
    
    # Environment configuration
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # CORS configuration
    # Añadir http://localhost:5173 para aceptar peticiones del frontend de Vite
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",  # Frontend Vite
        "http://localhost:3000",  # Frontend alternativo (por si se usa otro puerto)
        "http://localhost:8080",  # Frontend alternativo (por si se usa otro puerto)
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            if s.startswith("[") and s.endswith("]"):
                try:
                    data = json.loads(s)
                    if isinstance(data, list):
                        return [str(i).strip() for i in data]
                except Exception:
                    # Fallback to comma-separated parsing
                    return [i.strip() for i in s.strip("[]").split(",") if i.strip()]
            return [i.strip() for i in s.split(",") if i.strip()]
        elif isinstance(v, list):
            return [str(i).strip() for i in v]
        raise ValueError(v)

    # Supabase settings - usar los valores de .env o los predeterminados
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "https://aupmnxxauxasetwnqkma.supabase.co")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    # Redis Configuration
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Celery Configuration
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

    # JWT Configuration
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "your_jwt_secret_key_here")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

    # ML Configuration
    ML_MODEL_PATH: str = os.getenv("ML_MODEL_PATH", "./models/")
    ML_FEATURE_CACHE_TTL: int = int(os.getenv("ML_FEATURE_CACHE_TTL", "3600"))

    # Notification Configuration
    NOTIFICATION_CACHE_TTL: int = int(os.getenv("NOTIFICATION_CACHE_TTL", "3600"))
    DEFAULT_NOTIFICATION_LANGUAGE: str = os.getenv("DEFAULT_NOTIFICATION_LANGUAGE", "es")

    # Database connection settings for Supabase Pooler
    DB_USER: str = os.getenv("DB_USER", "postgres.aupmnxxauxasetwnqkma")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_HOST: str = os.getenv("DB_HOST", "aws-0-us-west-1.pooler.supabase.com")
    DB_PORT: str = os.getenv("DB_PORT", "5432")
    DB_NAME: str = os.getenv("DB_NAME", "postgres")
    
    # Database URL - Para desarrollo, usar SQLite si no hay variable de entorno
    @property
    def DATABASE_URL(self) -> str:
        """Build the PostgreSQL connection string or fallback to SQLite"""
        if self.DB_PASSWORD:
            # Usar PostgreSQL si hay contraseña
            return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        
        # Si no hay contraseña configurada, usar SQLite para desarrollo
        return "sqlite:///./micropymes.db"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # case_sensitive=True,  # default behavior is case-sensitive
    )


# Instancia singleton de configuración
settings = Settings() 