"""
business.py — Schemas Pydantic para el modelo Negocio
========================================================
FASE 2 — Desktop local. Sin Supabase.

Refleja exactamente el modelo ORM `Negocio` en orm_models.py.
El campo `openai_api_key` se expone para lectura/escritura desde
la pantalla de configuración (Fase 5 usará el keychain del SO;
por ahora se almacena en la DB como texto plano con la advertencia
correspondiente).
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class NegocioBase(BaseModel):
    """Campos comunes a todas las operaciones sobre Negocio."""
    nombre: str = Field(..., min_length=1, max_length=200, description="Nombre del negocio")
    descripcion: Optional[str] = Field(None, description="Descripción del negocio")
    direccion: Optional[str] = Field(None, max_length=300)
    telefono: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=150)
    logo_url: Optional[str] = Field(None, max_length=500)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

class NegocioCreate(NegocioBase):
    """Datos requeridos para crear un nuevo negocio (usado en /auth/setup)."""
    pass


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

class NegocioUpdate(BaseModel):
    """
    Actualización parcial del negocio.
    Todos los campos son opcionales para soportar PATCH.
    """
    nombre: Optional[str] = Field(None, min_length=1, max_length=200)
    descripcion: Optional[str] = None
    direccion: Optional[str] = Field(None, max_length=300)
    telefono: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=150)
    logo_url: Optional[str] = Field(None, max_length=500)
    openai_api_key: Optional[str] = Field(
        None,
        max_length=200,
        description=(
            "API Key de OpenAI para el módulo de importación de catálogos PDF. "
            "Se almacena en la DB local. En producción se migrará al keychain del SO."
        ),
    )


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

class NegocioResponse(NegocioBase):
    """
    Respuesta completa del negocio.
    NOTA: `openai_api_key` se enmascara en la respuesta (solo se indica
    si está configurada o no). Para actualizar la key usar PUT/PATCH.
    """
    id: str
    openai_api_key_configurada: bool = Field(
        False,
        description="True si hay una API Key de OpenAI configurada (el valor real no se expone).",
    )
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None

    class Config:
        from_attributes = True


class NegocioConfigResponse(NegocioResponse):
    """
    Respuesta extendida para la pantalla de configuración.
    Incluye la key enmascarada para que el frontend pueda mostrar
    los últimos 4 caracteres.
    """
    openai_api_key_hint: Optional[str] = Field(
        None,
        description="Últimos 4 caracteres de la API Key (para confirmación visual). None si no está configurada.",
    )


# ---------------------------------------------------------------------------
# Aliases de compatibilidad (para código legacy que importa Business/BusinessCreate)
# ---------------------------------------------------------------------------

class BusinessCreate(BaseModel):
    """Alias legacy — usar NegocioCreate en código nuevo."""
    nombre: str


class Business(BaseModel):
    """
    Alias legacy para compatibilidad con businesses.py (Supabase-era).
    Se conserva para no romper imports mientras se migra businesses.py en Fase 3.
    """
    id: str
    nombre: str
    creada_en: Optional[datetime] = None
    rol: Optional[str] = None

    class Config:
        from_attributes = True