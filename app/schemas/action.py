"""
Pydantic schemas for Action System API.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from enum import Enum


class ActionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    AUTO_APPROVED = "auto_approved"
    MANUAL_APPROVED = "manual_approved"
    REJECTED = "rejected"


class ActionExecutionBase(BaseModel):
    """Base schema for action execution"""
    execution_id: str
    tenant_id: str
    action_type: str
    action_description: str
    status: ActionStatus
    approval_status: ApprovalStatus
    confidence_score: Optional[float] = None
    created_at: datetime
    executed_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


class ActionExecutionResponse(ActionExecutionBase):
    """Response schema for action execution details"""
    prediction_id: Optional[str] = None
    llm_response_id: Optional[str] = None
    action_params: Dict[str, Any]
    impact_assessment: Dict[str, Any]
    execution_result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    rollback_status: Optional[str] = None

    @classmethod
    def from_execution(cls, execution) -> "ActionExecutionResponse":
        """Create response from ActionExecution dataclass"""
        return cls(
            execution_id=execution.id,
            tenant_id=execution.tenant_id,
            action_type=execution.action.action_type,
            action_description=f"Automated {execution.action.action_type} action",
            status=execution.status,
            approval_status=execution.approval_status,
            confidence_score=execution.action.confidence,
            created_at=execution.created_at,
            executed_at=None,  # Would come from DB
            approved_by=None,  # Would come from DB
            approved_at=None,  # Would come from DB
            prediction_id=execution.prediction_id,
            llm_response_id=execution.llm_response_id,
            action_params=execution.action.parameters,
            impact_assessment=execution.impact_assessment,
            execution_result=None,
            error_message=None,
            rollback_status=None
        )


class ActionExecutionListResponse(BaseModel):
    """Response schema for list of action executions"""
    executions: List[ActionExecutionResponse]
    total: int
    limit: int
    offset: int


class ActionApprovalBase(BaseModel):
    """Base schema for action approval"""
    approval_id: str
    execution_id: str
    tenant_id: str
    action_type: str
    action_description: str
    impact_summary: str
    confidence_score: Optional[float] = None
    status: ApprovalStatus
    priority: str = "medium"
    created_at: datetime
    expires_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None


class ActionApprovalResponse(ActionApprovalBase):
    """Response schema for approval details"""
    decision_notes: Optional[str] = None


class ActionApprovalListResponse(BaseModel):
    """Response schema for list of approvals"""
    approvals: List[ActionApprovalResponse]
    total: int
    limit: int
    offset: int


class ActionApprovalRequest(BaseModel):
    """Request schema for approval/rejection actions"""
    notes: Optional[str] = Field(None, max_length=500, description="Optional notes for the decision")


class TenantActionSettingsBase(BaseModel):
    """Base schema for tenant action settings"""
    automation_enabled: bool = False
    approval_required: bool = True
    auto_approval_threshold: float = Field(0.9, ge=0.0, le=1.0)
    max_actions_per_hour: int = Field(10, ge=1, le=1000)
    max_actions_per_day: int = Field(50, ge=1, le=10000)
    allowed_action_types: List[str] = Field(default_factory=lambda: ["create_task", "send_notification"])
    canary_percentage: float = Field(0.0, ge=0.0, le=1.0)
    safety_mode: str = Field("strict")

    @field_validator('safety_mode')
    @classmethod
    def validate_safety_mode(cls, v):
        if v not in ['strict', 'moderate', 'permissive']:
            raise ValueError('safety_mode must be one of: strict, moderate, permissive')
        return v
    notification_on_auto_action: bool = True


class TenantActionSettingsResponse(TenantActionSettingsBase):
    """Response schema for tenant settings"""
    tenant_id: str
    created_at: datetime
    updated_at: datetime


class TenantActionSettingsUpdate(BaseModel):
    """Update schema for tenant action settings"""
    automation_enabled: Optional[bool] = None
    approval_required: Optional[bool] = None
    auto_approval_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_actions_per_hour: Optional[int] = Field(None, ge=1, le=1000)
    max_actions_per_day: Optional[int] = Field(None, ge=1, le=10000)
    allowed_action_types: Optional[List[str]] = None
    canary_percentage: Optional[float] = Field(None, ge=0.0, le=1.0)
    safety_mode: Optional[str] = Field(None)

    @field_validator('safety_mode')
    @classmethod
    def validate_update_safety_mode(cls, v):
        if v is not None and v not in ['strict', 'moderate', 'permissive']:
            raise ValueError('safety_mode must be one of: strict, moderate, permissive')
        return v
    notification_on_auto_action: Optional[bool] = None


class ActionDefinitionResponse(BaseModel):
    """Response schema for action definitions"""
    id: str
    action_type: str
    name: str
    description: Optional[str] = None
    category: str
    requires_approval: bool
    impact_level: str
    rollback_supported: bool
    config_schema: Dict[str, Any]
    ui_component: Optional[str] = None
    is_active: bool


class ActionDefinitionsListResponse(BaseModel):
    """Response schema for list of action definitions"""
    definitions: List[ActionDefinitionResponse]


class ActionExecutionStats(BaseModel):
    """Statistics for action executions"""
    total_executions: int
    successful_executions: int
    failed_executions: int
    pending_approvals: int
    auto_approved: int
    manual_approved: int
    rejected: int
    rolled_back: int
    average_execution_time: Optional[float] = None
    success_rate: float


class ActionAuditLogEntry(BaseModel):
    """Schema for audit log entries"""
    id: str
    tenant_id: str
    execution_id: Optional[str] = None
    approval_id: Optional[str] = None
    event_type: str
    event_description: str
    user_id: Optional[str] = None
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime


class ActionAuditLogResponse(BaseModel):
    """Response schema for audit log"""
    entries: List[ActionAuditLogEntry]
    total: int
    limit: int
    offset: int