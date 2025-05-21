import os
from typing import List, Union
from pydantic import AnyHttpUrl, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "MicroPymes"
    
    # Environment configuration
    DEBUG: bool = True  # Establecer en False para producción
    
    # CORS configuration
    # Añadir http://localhost:5173 para aceptar peticiones del frontend de Vite
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = [
        "http://localhost:5173",  # Frontend Vite
        "http://localhost:3000",  # Frontend alternativo (por si se usa otro puerto)
        "http://localhost:8080",  # Frontend alternativo (por si se usa otro puerto)
    ]

    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # Supabase settings - usar los valores de .env o los predeterminados
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "https://aupmnxxauxasetwnqkma.supabase.co")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    
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
    
    class Config:
        case_sensitive = True
        env_file = ".env"
        env_file_encoding = "utf-8"


# Instancia singleton de configuración
settings = Settings() 