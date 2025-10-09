"""
Action System API endpoints - Manage automated actions, approvals, and executions.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.services.safe_action_engine import safe_action_engine
from app.schemas.action import (
    ActionExecutionResponse,
    ActionApprovalResponse,
    ActionApprovalRequest,
    ActionExecutionListResponse,
    ActionApprovalListResponse,
    TenantActionSettingsResponse,
    TenantActionSettingsUpdate
)

router = APIRouter()


@router.get("/executions", response_model=ActionExecutionListResponse)
async def get_action_executions(
    tenant_id: str = Depends(deps.get_current_tenant_id),
    status: Optional[str] = Query(None, description="Filter by execution status"),
    action_type: Optional[str] = Query(None, description="Filter by action type"),
    limit: int = Query(50, description="Maximum number of results"),
    offset: int = Query(0, description="Pagination offset"),
    current_user: dict = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Get action executions for the tenant with optional filtering.
    """
    try:
        # TODO: Implement database query for action executions
        # For now, return empty response
        return ActionExecutionListResponse(
            executions=[],
            total=0,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch action executions: {str(e)}")


@router.get("/executions/{execution_id}", response_model=ActionExecutionResponse)
async def get_action_execution(
    execution_id: str,
    tenant_id: str = Depends(deps.get_current_tenant_id),
    current_user: dict = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Get details of a specific action execution.
    """
    try:
        execution = await safe_action_engine._get_action_execution(execution_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Action execution not found")

        if execution.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="Access denied")

        return ActionExecutionResponse.from_execution(execution)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch action execution: {str(e)}")


@router.post("/executions/{execution_id}/approve")
async def approve_action(
    execution_id: str,
    approval_data: ActionApprovalRequest,
    tenant_id: str = Depends(deps.get_current_tenant_id),
    current_user: dict = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Approve an action for execution.
    """
    try:
        success = await safe_action_engine.approve_action(
            execution_id=execution_id,
            approved_by=current_user.get('id', 'system'),
            notes=approval_data.notes or ""
        )

        if not success:
            raise HTTPException(status_code=400, detail="Failed to approve action")

        return {"message": "Action approved successfully", "execution_id": execution_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to approve action: {str(e)}")


@router.post("/executions/{execution_id}/reject")
async def reject_action(
    execution_id: str,
    approval_data: ActionApprovalRequest,
    tenant_id: str = Depends(deps.get_current_tenant_id),
    current_user: dict = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Reject an action execution.
    """
    try:
        success = await safe_action_engine.reject_action(
            execution_id=execution_id,
            rejected_by=current_user.get('id', 'system'),
            reason=approval_data.notes or "Rejected by user"
        )

        if not success:
            raise HTTPException(status_code=400, detail="Failed to reject action")

        return {"message": "Action rejected successfully", "execution_id": execution_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reject action: {str(e)}")


@router.post("/executions/{execution_id}/rollback")
async def rollback_action(
    execution_id: str,
    rollback_reason: str = Query(..., description="Reason for rollback"),
    tenant_id: str = Depends(deps.get_current_tenant_id),
    current_user: dict = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Rollback a completed action if supported.
    """
    try:
        success = await safe_action_engine.rollback_action(
            execution_id=execution_id,
            rollback_reason=rollback_reason
        )

        if not success:
            raise HTTPException(status_code=400, detail="Failed to rollback action or rollback not supported")

        return {"message": "Action rolled back successfully", "execution_id": execution_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rollback action: {str(e)}")


@router.get("/approvals", response_model=ActionApprovalListResponse)
async def get_pending_approvals(
    tenant_id: str = Depends(deps.get_current_tenant_id),
    assigned_to_me: bool = Query(False, description="Only show approvals assigned to current user"),
    limit: int = Query(50, description="Maximum number of results"),
    offset: int = Query(0, description="Pagination offset"),
    current_user: dict = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Get pending action approvals for the tenant.
    """
    try:
        # TODO: Implement database query for pending approvals
        # For now, return empty response
        return ActionApprovalListResponse(
            approvals=[],
            total=0,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch pending approvals: {str(e)}")


@router.get("/approvals/{approval_id}", response_model=ActionApprovalResponse)
async def get_approval_details(
    approval_id: str,
    tenant_id: str = Depends(deps.get_current_tenant_id),
    current_user: dict = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Get details of a specific approval request.
    """
    try:
        # TODO: Implement database query for approval details
        raise HTTPException(status_code=404, detail="Approval not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch approval details: {str(e)}")


@router.get("/settings", response_model=TenantActionSettingsResponse)
async def get_tenant_action_settings(
    tenant_id: str = Depends(deps.get_current_tenant_id),
    current_user: dict = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Get action automation settings for the tenant.
    """
    try:
        settings = await safe_action_engine._get_tenant_action_settings(tenant_id)
        return TenantActionSettingsResponse(**settings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch tenant settings: {str(e)}")


@router.put("/settings", response_model=TenantActionSettingsResponse)
async def update_tenant_action_settings(
    settings_update: TenantActionSettingsUpdate,
    tenant_id: str = Depends(deps.get_current_tenant_id),
    current_user: dict = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Update action automation settings for the tenant.
    Requires admin permissions.
    """
    try:
        # Check admin permissions
        if not current_user.get('is_admin', False):
            raise HTTPException(status_code=403, detail="Admin permissions required")

        # TODO: Implement settings update in database
        # For now, return the input as if updated
        updated_settings = settings_update.dict()
        updated_settings['tenant_id'] = tenant_id

        return TenantActionSettingsResponse(**updated_settings)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update tenant settings: {str(e)}")


@router.get("/definitions")
async def get_action_definitions(
    tenant_id: str = Depends(deps.get_current_tenant_id),
    current_user: dict = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Get available action definitions.
    """
    try:
        # TODO: Implement database query for action definitions
        # For now, return hardcoded definitions
        definitions = [
            {
                "id": "create_task",
                "action_type": "create_task",
                "name": "Crear Tarea",
                "description": "Crea una nueva tarea en el sistema",
                "category": "task_management",
                "requires_approval": True,
                "impact_level": "medium",
                "rollback_supported": True,
                "config_schema": {
                    "type": "object",
                    "properties": {
                        "titulo": {"type": "string", "maxLength": 200},
                        "descripcion": {"type": "string", "maxLength": 1000},
                        "prioridad": {"type": "string", "enum": ["baja", "media", "alta", "urgente"]}
                    },
                    "required": ["titulo"]
                }
            },
            {
                "id": "send_notification",
                "action_type": "send_notification",
                "name": "Enviar Notificación",
                "description": "Envía una notificación al usuario",
                "category": "communication",
                "requires_approval": False,
                "impact_level": "low",
                "rollback_supported": False,
                "config_schema": {
                    "type": "object",
                    "properties": {
                        "titulo": {"type": "string", "maxLength": 200},
                        "mensaje": {"type": "string", "maxLength": 1000},
                        "tipo": {"type": "string", "enum": ["info", "warning", "error", "success"]}
                    },
                    "required": ["titulo", "mensaje"]
                }
            }
        ]

        return {"definitions": definitions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch action definitions: {str(e)}")


@router.post("/executions/{execution_id}/execute")
async def execute_approved_action(
    execution_id: str,
    tenant_id: str = Depends(deps.get_current_tenant_id),
    current_user: dict = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Manually trigger execution of an approved action.
    """
    try:
        success = await safe_action_engine.execute_approved_action(execution_id)

        if not success:
            raise HTTPException(status_code=400, detail="Failed to execute action")

        return {"message": "Action executed successfully", "execution_id": execution_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute action: {str(e)}")