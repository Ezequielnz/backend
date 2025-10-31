from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.context import BusinessScopedClientDep, ScopedClientContext
from app.core.feature_flags import BRANCH_INVENTORY_MODES, is_feature_enabled
from app.schemas.branch_settings import BranchSettings
from app.schemas.stock_transfer import StockTransfer, StockTransferCreate
from app.services.stock_transfer_service import (
    StockTransferError,
    StockTransferNotAllowedError,
    StockTransferNotFoundError,
    StockTransferService,
    StockTransferStateError,
    StockTransferValidationError,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _ensure_feature_enabled() -> None:
    if not is_feature_enabled(BRANCH_INVENTORY_MODES):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Branch inventory modes feature is not enabled.",
        )


def _build_service(scoped: ScopedClientContext) -> StockTransferService:
    settings_payload = scoped.context.branch_settings or {}
    settings: BranchSettings | dict[str, object] | None = None
    if settings_payload:
        try:
            settings = BranchSettings(**settings_payload)
        except Exception:  # pragma: no cover - defensive against malformed payloads
            logger.warning(
                "Could not parse branch settings for business %s",
                scoped.context.business_id,
            )
            settings = settings_payload

    return StockTransferService(
        scoped.client,
        scoped.context.business_id,
        scoped.context.user_id,
        settings,
    )


@router.get("/", response_model=List[StockTransfer])
async def list_stock_transfers(
    estado: Optional[str] = Query(None, description="Filtrar por estado de la transferencia."),
    origen_sucursal_id: Optional[UUID] = Query(None, description="Filtrar por sucursal de origen."),
    destino_sucursal_id: Optional[UUID] = Query(None, description="Filtrar por sucursal de destino."),
    limit: int = Query(50, ge=1, le=200, description="Cantidad maxima de registros a devolver."),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> List[StockTransfer]:
    """
    Retrieve stock transfers for the current business.
    """
    _ensure_feature_enabled()
    service = _build_service(scoped)

    try:
        return service.list_transfers(
            estado=estado,
            origen_sucursal_id=str(origen_sucursal_id) if origen_sucursal_id else None,
            destino_sucursal_id=str(destino_sucursal_id) if destino_sucursal_id else None,
            limit=limit,
        )
    except StockTransferValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except StockTransferError as exc:
        logger.exception("Failed to list stock transfers for negocio %s", scoped.context.business_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudieron obtener las transferencias de stock.",
        ) from exc


@router.post("/", response_model=StockTransfer, status_code=status.HTTP_201_CREATED)
async def create_stock_transfer(
    payload: StockTransferCreate,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> StockTransfer:
    """
    Create a new stock transfer between branches of the current business.
    """
    _ensure_feature_enabled()
    service = _build_service(scoped)

    try:
        return service.create_transfer(payload)
    except StockTransferNotAllowedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except StockTransferValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except StockTransferError as exc:
        logger.exception("Failed to create stock transfer for business %s", scoped.context.business_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo crear la transferencia de stock.",
        ) from exc


@router.post("/{transfer_id}/confirm", response_model=StockTransfer)
async def confirm_stock_transfer(
    transfer_id: UUID,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> StockTransfer:
    """
    Confirm a draft stock transfer, deducting inventory from the origin branch.
    """
    _ensure_feature_enabled()
    service = _build_service(scoped)

    try:
        return service.confirm_transfer(transfer_id)
    except StockTransferNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except StockTransferStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except StockTransferValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except StockTransferNotAllowedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except StockTransferError as exc:
        logger.exception("Failed to confirm transfer %s", transfer_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo confirmar la transferencia.",
        ) from exc


@router.post("/{transfer_id}/receive", response_model=StockTransfer)
async def receive_stock_transfer(
    transfer_id: UUID,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> StockTransfer:
    """
    Mark a confirmed transfer as received, adding stock to the destination branch.
    """
    _ensure_feature_enabled()
    service = _build_service(scoped)

    try:
        return service.receive_transfer(transfer_id)
    except StockTransferNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except StockTransferStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except StockTransferNotAllowedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except StockTransferError as exc:
        logger.exception("Failed to receive transfer %s", transfer_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo marcar la transferencia como recibida.",
        ) from exc


@router.delete("/{transfer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stock_transfer(
    transfer_id: UUID,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Response:
    """
    Delete a draft stock transfer and its items.
    """
    _ensure_feature_enabled()
    service = _build_service(scoped)

    try:
        service.delete_transfer(transfer_id)
    except StockTransferNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except StockTransferStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except StockTransferNotAllowedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except StockTransferError as exc:
        logger.exception("Failed to delete transfer %s", transfer_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo eliminar la transferencia de stock.",
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
