"""
negocio.py — Endpoint de configuración del negocio (desktop local)
====================================================================
FASE 2 — Paso 5: Agregar campo `openai_api_key` en la tabla de
configuración del negocio.

Endpoints:
  GET  /negocio/config          → lee la configuración del negocio del usuario autenticado
  PUT  /negocio/config          → actualiza la configuración (nombre, email, openai_api_key, etc.)
  POST /negocio/config/api-key  → actualiza solo la API Key de OpenAI

En la versión desktop hay exactamente un negocio por instalación.
Todos los endpoints requieren JWT local válido.

NOTA sobre openai_api_key:
  Se almacena en SQLite en texto plano en esta fase.
  En Fase 5 se migrará al keychain del SO (Windows Credential Manager /
  macOS Keychain) a través de Electron safeStorage.
  Por eso la API key NUNCA se devuelve en texto plano en las respuestas;
  solo se indica si está configurada y se muestran los últimos 4 caracteres.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, UserData
from app.models.orm_models import Negocio
from app.schemas.business import NegocioUpdate, NegocioConfigResponse
from pydantic import BaseModel, Field

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_negocio_del_usuario(user: UserData, db: Session) -> Negocio:
    """
    Obtiene el negocio del usuario autenticado desde SQLite.
    Lanza 404 si no existe (situación anormal en desktop).
    """
    negocio_id = user.get("negocio_id")
    if not negocio_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El usuario no tiene un negocio asociado.",
        )

    negocio = db.query(Negocio).filter(Negocio.id == negocio_id).first()
    if not negocio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Negocio no encontrado.",
        )
    return negocio


def _build_config_response(negocio: Negocio) -> dict:
    """
    Construye la respuesta de configuración enmascarando la API key.
    El valor real de openai_api_key nunca se devuelve en la respuesta.
    """
    key: Optional[str] = negocio.openai_api_key
    key_hint: Optional[str] = None
    if key and len(key) >= 4:
        key_hint = "..." + key[-4:]

    return {
        "id": negocio.id,
        "nombre": negocio.nombre,
        "descripcion": negocio.descripcion,
        "direccion": negocio.direccion,
        "telefono": negocio.telefono,
        "email": negocio.email,
        "logo_url": negocio.logo_url,
        "openai_api_key_configurada": bool(key),
        "openai_api_key_hint": key_hint,
        "creado_en": negocio.creado_en.isoformat() if negocio.creado_en else None,
        "actualizado_en": negocio.actualizado_en.isoformat() if negocio.actualizado_en else None,
    }


# ---------------------------------------------------------------------------
# Schemas locales (solo para este endpoint)
# ---------------------------------------------------------------------------

class ApiKeyUpdate(BaseModel):
    """Cuerpo para actualizar solo la API Key de OpenAI."""
    openai_api_key: str = Field(
        ...,
        min_length=10,
        description="API Key de OpenAI (sk-...).",
    )


# ---------------------------------------------------------------------------
# GET /negocio/config
# ---------------------------------------------------------------------------

@router.get("/config", response_model=dict)
async def get_negocio_config(
    current_user: UserData = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Devuelve la configuración del negocio del usuario autenticado.

    La `openai_api_key` **no** se devuelve en texto plano; solo se indica
    si está configurada (`openai_api_key_configurada: bool`) y se muestran
    los últimos 4 caracteres (`openai_api_key_hint`).
    """
    negocio = _get_negocio_del_usuario(current_user, db)
    return _build_config_response(negocio)


# ---------------------------------------------------------------------------
# PUT /negocio/config
# ---------------------------------------------------------------------------

@router.put("/config", response_model=dict)
async def update_negocio_config(
    data: NegocioUpdate,
    current_user: UserData = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Actualiza la configuración del negocio.

    Acepta cualquier combinación de campos (PATCH semántico aunque
    sea PUT). Los campos no enviados no se modifican.

    Si se envía `openai_api_key`, se almacena en la DB.
    La respuesta no incluye el valor real de la key.
    """
    negocio = _get_negocio_del_usuario(current_user, db)

    # Aplicar solo los campos enviados (exclude_unset)
    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(negocio, field, value)

    try:
        db.commit()
        db.refresh(negocio)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error actualizando la configuración: {e}",
        )

    return _build_config_response(negocio)


# ---------------------------------------------------------------------------
# POST /negocio/config/api-key
# ---------------------------------------------------------------------------

@router.post("/config/api-key", response_model=dict)
async def set_openai_api_key(
    data: ApiKeyUpdate,
    current_user: UserData = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Actualiza solo la API Key de OpenAI del negocio.

    Endpoint dedicado para facilitar la integración desde la pantalla de
    configuración sin necesidad de enviar todos los campos del negocio.

    FASE 5: Este endpoint se reemplazará por almacenamiento en el keychain
    del SO (Windows Credential Manager / macOS Keychain) via Electron.
    """
    negocio = _get_negocio_del_usuario(current_user, db)
    negocio.openai_api_key = data.openai_api_key.strip()

    try:
        db.commit()
        db.refresh(negocio)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error guardando la API Key: {e}",
        )

    return {
        "mensaje": "API Key de OpenAI actualizada correctamente.",
        "openai_api_key_configurada": True,
        "openai_api_key_hint": "..." + data.openai_api_key.strip()[-4:],
    }


# ---------------------------------------------------------------------------
# DELETE /negocio/config/api-key
# ---------------------------------------------------------------------------

@router.delete("/config/api-key", response_model=dict)
async def delete_openai_api_key(
    current_user: UserData = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Elimina la API Key de OpenAI del negocio (la pone en NULL).
    """
    negocio = _get_negocio_del_usuario(current_user, db)
    negocio.openai_api_key = None

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error eliminando la API Key: {e}",
        )

    return {
        "mensaje": "API Key de OpenAI eliminada correctamente.",
        "openai_api_key_configurada": False,
        "openai_api_key_hint": None,
    }
