from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.context import BusinessScopedClientDep, ScopedClientContext
from app.core.feature_flags import BRANCH_INVENTORY_MODES, is_feature_enabled
from app.schemas.branch_settings import BranchSettings, BranchSettingsUpdate
from app.services.branch_settings_service import BranchSettingsService

logger = logging.getLogger(__name__)

router = APIRouter()


def _ensure_feature_enabled() -> None:
    if not is_feature_enabled(BRANCH_INVENTORY_MODES):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Branch inventory modes feature is not enabled.",
        )


@router.get("/", response_model=BranchSettings)
async def get_branch_settings(scoped: ScopedClientContext = Depends(BusinessScopedClientDep)) -> BranchSettings:
    """
    Retrieve the branch configuration (negocio_configuracion) for the given business.
    """
    _ensure_feature_enabled()

    service = BranchSettingsService(scoped.client, scoped.context.business_id)
    settings = service.fetch(ensure_exists=True)
    if settings is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No branch settings found for this business.",
        )
    return settings


@router.put("/", response_model=BranchSettings)
async def update_branch_settings(
    payload: BranchSettingsUpdate,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> BranchSettings:
    """
    Update negocio_configuracion for the current business. Restricted to admin/owner roles.
    """
    _ensure_feature_enabled()

    if scoped.context.user_role not in {"owner", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los administradores o dueños pueden modificar las preferencias del negocio.",
        )

    service = BranchSettingsService(scoped.client, scoped.context.business_id)

    try:
        return service.update(payload)
    except Exception as exc:  # pragma: no cover - Supabase client raises generic exceptions
        logger.exception("Failed to update branch settings for negocio %s", scoped.context.business_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudieron actualizar las preferencias del negocio; intente nuevamente.",
        ) from exc
