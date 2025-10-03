import os
import json
from typing import ClassVar, cast
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
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:5173",  # Frontend Vite
        "http://localhost:3000",  # Frontend alternativo (por si se usa otro puerto)
        "http://localhost:8080",  # Frontend alternativo (por si se usa otro puerto)
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: object) -> list[str]:
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            if s.startswith("[") and s.endswith("]"):
                try:
                    parsed_obj: object = cast(object, json.loads(s))
                    if isinstance(parsed_obj, list):
                        data_list: list[object] = cast(list[object], parsed_obj)
                        return [str(i).strip() for i in data_list]
                except Exception:
                    # Fallback to comma-separated parsing
                    return [i.strip() for i in s.strip("[]").split(",") if i.strip()]
            return [i.strip() for i in s.split(",") if i.strip()]
        elif isinstance(v, list):
            v_list: list[object] = cast(list[object], v)
            return [str(i).strip() for i in v_list]
        raise ValueError(str(v))

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
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    # Embedding / LLM settings (used by Phase 3 LLM Reasoning Core)
    EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "384"))
    # ML Tuning Flags
    ML_CV_FOLDS: int = int(os.getenv("ML_CV_FOLDS", "3"))
    ML_SEASONALITY_MODE: str = os.getenv("ML_SEASONALITY_MODE", "additive")  # additive|multiplicative
    ML_HOLIDAYS_COUNTRY: str = os.getenv("ML_HOLIDAYS_COUNTRY", "")  # e.g., AR, US; empty to disable
    ML_LOG_TRANSFORM: bool = os.getenv("ML_LOG_TRANSFORM", "false").lower() == "true"
    ML_MODEL_CANDIDATES: str = os.getenv("ML_MODEL_CANDIDATES", "prophet")  # comma-separated: prophet,sarimax
    ML_SELECT_BEST: bool = os.getenv("ML_SELECT_BEST", "false").lower() == "true"
    ML_CV_PRIMARY_METRIC: str = os.getenv("ML_CV_PRIMARY_METRIC", "mape")  # mape|smape|mae|rmse
    # SARIMAX options (tuples as comma-separated). Leave seasonal empty to disable seasonal part
    ML_SARIMAX_ORDER: str = os.getenv("ML_SARIMAX_ORDER", "1,1,1")
    ML_SARIMAX_SEASONAL: str = os.getenv("ML_SARIMAX_SEASONAL", "")  # e.g., "1,1,1,7"
    # Anomaly detection options
    ML_ANOMALY_METHOD: str = os.getenv("ML_ANOMALY_METHOD", "iforest")  # iforest|stl_resid
    ML_STL_PERIOD: int = int(os.getenv("ML_STL_PERIOD", "7"))

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
    
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


# Instancia singleton de configuración
settings = Settings() 