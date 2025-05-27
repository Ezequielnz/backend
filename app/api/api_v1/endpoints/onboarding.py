from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from supabase.client import Client

from app.db.supabase_client import get_supabase_client
from app.api import deps
from app.schemas.usuario import Usuario as CurrentUserSchema
from app.schemas.onboarding import (
    ConfiguracionUsuarioResponse,
    ConfiguracionUsuarioUpdate,
    OnboardingProgresoResponse,
    PasoProgresoUpdate,
    KNOWN_ONBOARDING_STEPS,
)

router = APIRouter()

TABLE_NAME = "configuracion_usuario" # Assumed table name

async def _get_or_initialize_user_config(
    supabase: Client, user_id: str
) -> Dict[str, Any]:
    """
    Fetches user configuration. If not found, initializes with default values.
    This function does NOT create a record in DB if not found, but returns a default dict.
    The upsert operation in POST /configuracion/ will handle the actual creation.
    """
    response = await supabase.table(TABLE_NAME).select("*").eq("usuario_id", user_id).maybe_single().execute()
    if response.data:
        return response.data
    else:
        # Return a default structure if no config exists yet for this user
        return {
            "usuario_id": user_id,
            "nombre_empresa": None,
            "direccion_empresa": None,
            "cuit_empresa": None,
            "telefono_empresa": None,
            "email_empresa": None,
            "config_afip_json": {},
            "config_whatsapp_json": {},
            "onboarding_pasos_completados": {},
            "creado_en": None, # Will be set on actual creation
            "actualizado_en": None
        }

def _calculate_progress(pasos_completados: Dict[str, bool]) -> float:
    if not KNOWN_ONBOARDING_STEPS:
        return 100.0 # Or 0.0, depending on desired behavior if no steps defined
    
    completed_count = sum(1 for paso, completado in pasos_completados.items() if paso in KNOWN_ONBOARDING_STEPS and completado)
    progress_percentage = (completed_count / len(KNOWN_ONBOARDING_STEPS)) * 100
    return round(progress_percentage, 2)

@router.get("/configuracion/", response_model=ConfiguracionUsuarioResponse)
async def get_user_configuration(
    *,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
) -> Any:
    """
    Get the current authenticated user's onboarding configuration.
    Initializes with default values if no configuration exists yet (but doesn't save it).
    """
    user_id_str = str(current_user.id)
    config_data = await _get_or_initialize_user_config(supabase, user_id_str)
    return ConfiguracionUsuarioResponse(**config_data)


@router.post("/configuracion/", response_model=ConfiguracionUsuarioResponse)
async def update_user_configuration(
    *,
    config_in: ConfiguracionUsuarioUpdate,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
) -> Any:
    """
    Create or update the current authenticated user's onboarding configuration (upsert).
    """
    user_id_str = str(current_user.id)
    update_data = config_in.model_dump(exclude_unset=True)
    
    if not update_data:
        # If nothing to update, fetch and return existing or default config
        # This behavior can be debated; some might prefer raising a 400.
        existing_config_data = await _get_or_initialize_user_config(supabase, user_id_str)
        return ConfiguracionUsuarioResponse(**existing_config_data)

    # Prepare data for upsert
    data_to_upsert = {
        "usuario_id": user_id_str,
        **update_data,
        "actualizado_en": datetime.now(timezone.utc).isoformat()
    }
    
    # For a true "upsert" that also sets "creado_en" on initial insert:
    # This requires checking if the record exists first, or handling it via DB trigger/default.
    # Supabase upsert with 'on_conflict' on 'usuario_id' will insert or update.
    # We need to ensure 'creado_en' is set appropriately.
    # A simple way is to fetch first, if not present, add 'creado_en'.
    
    existing_data_check = await supabase.table(TABLE_NAME).select("usuario_id").eq("usuario_id", user_id_str).maybe_single().execute()
    if not existing_data_check.data:
        data_to_upsert["creado_en"] = datetime.now(timezone.utc).isoformat()

    response = await supabase.table(TABLE_NAME).upsert(data_to_upsert, on_conflict="usuario_id").select("*").single().execute()

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save user configuration."
        )
    return ConfiguracionUsuarioResponse(**response.data)


@router.get("/progreso/", response_model=OnboardingProgresoResponse)
async def get_onboarding_progress(
    *,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
) -> Any:
    """
    Get the current authenticated user's onboarding progress.
    """
    user_id_str = str(current_user.id)
    config_data = await _get_or_initialize_user_config(supabase, user_id_str)
    
    pasos_completados = config_data.get("onboarding_pasos_completados", {})
    porcentaje = _calculate_progress(pasos_completados)
    
    return OnboardingProgresoResponse(
        pasos_completados=pasos_completados,
        porcentaje_completado=porcentaje
    )

@router.post("/progreso/marcar_paso/", response_model=OnboardingProgresoResponse)
async def mark_onboarding_step(
    *,
    paso_update: PasoProgresoUpdate,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
) -> Any:
    """
    Mark a specific onboarding step as completed or not completed.
    """
    user_id_str = str(current_user.id)
    
    # Fetch current config or get defaults
    current_config = await _get_or_initialize_user_config(supabase, user_id_str)
    pasos_completados = current_config.get("onboarding_pasos_completados", {})
    
    # Update the specific step
    pasos_completados[paso_update.paso] = paso_update.completado
    
    # Prepare data for upsert
    data_to_upsert = {
        "usuario_id": user_id_str,
        "onboarding_pasos_completados": pasos_completados,
        "actualizado_en": datetime.now(timezone.utc).isoformat()
    }
    
    # Ensure 'creado_en' is set if this is the first interaction creating the record
    if current_config.get("creado_en") is None and not (await supabase.table(TABLE_NAME).select("usuario_id").eq("usuario_id", user_id_str).maybe_single().execute()).data:
        data_to_upsert["creado_en"] = datetime.now(timezone.utc).isoformat()
        # If it's the first time, and other fields are None, upsert might not set them as default.
        # It's better if the /onboarding/configuracion POST endpoint is called first to set initial details.
        # For this specific endpoint, we only focus on 'onboarding_pasos_completados'.

    response = await supabase.table(TABLE_NAME).upsert(data_to_upsert, on_conflict="usuario_id").select("*").single().execute()

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not update onboarding step '{paso_update.paso}'."
        )
    
    updated_pasos = response.data.get("onboarding_pasos_completados", {})
    porcentaje = _calculate_progress(updated_pasos)
    
    return OnboardingProgresoResponse(
        pasos_completados=updated_pasos,
        porcentaje_completado=porcentaje
    )
