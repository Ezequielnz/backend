"""
config.py — Configuración de MicroPymes Desktop
=================================================
Stack local: FastAPI + SQLite + SQLAlchemy.
Se eliminaron todas las referencias a Supabase, Redis, Celery y ML pipeline.
"""

import json
import os
from typing import ClassVar, cast

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Core ──────────────────────────────────────────────────────────────────
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "MicroPymes"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # ── CORS ──────────────────────────────────────────────────────────────────
    # En desktop el frontend Electron/Vite corre en localhost.
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:5173",   # Frontend Vite dev
        "http://localhost:3000",   # Alternativo
        "http://localhost:8080",   # Alternativo
    ]
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    FRONTEND_CONFIRMATION_PATH: str = os.getenv("FRONTEND_CONFIRMATION_PATH", "")

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: object) -> list[str]:
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            if s.startswith("[") and s.endswith("]"):
                try:
                    parsed: object = cast(object, json.loads(s))
                    if isinstance(parsed, list):
                        return [str(i).strip() for i in cast(list[object], parsed)]
                except Exception:
                    return [i.strip() for i in s.strip("[]").split(",") if i.strip()]
            return [i.strip() for i in s.split(",") if i.strip()]
        elif isinstance(v, list):
            return [str(i).strip() for i in cast(list[object], v)]
        raise ValueError(str(v))

    # ── Base de datos local (SQLite) ───────────────────────────────────────────
    # Siempre SQLite en modo desktop. La ruta puede sobreescribirse con
    # MICROPYMES_DB_URL para tests (:memory:) o rutas personalizadas.
    DATABASE_URL: str = os.getenv("MICROPYMES_DB_URL", "sqlite:///./micropymes.db")

    # ── Auth JWT local ─────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "changeme-in-production-desktop")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "10080")  # 7 días
    )

    # ── OpenAI (opcional — usado por pdf_parser para importar catálogos) ───────
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # ── Emails exentos de restricciones ───────────────────────────────────────
    EXEMPT_EMAILS: list[str] = []

    # ── Pydantic-settings ─────────────────────────────────────────────────────
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ── Propiedades de conveniencia ────────────────────────────────────────────
    @property
    def FRONTEND_CONFIRMATION_URL(self) -> str:
        """URL absoluta de confirmación para redirecciones del frontend."""
        base = self.FRONTEND_URL.rstrip("/") or "http://localhost:5173"
        path = self.FRONTEND_CONFIRMATION_PATH
        if not path:
            return base
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{base}{path}"


# Singleton de configuración
settings = Settings()
