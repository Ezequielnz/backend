"""
Safe Action Engine - Core orchestration for automated action execution with safety controls.
Handles approval gates, impact assessment, gradual rollout, and rollback capabilities.
"""
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

from app.core.config import settings
from app.services.action_parser import ParsedAction, action_parser_service
from app.db.supabase_client import get_supabase_client
from app.core.cache_manager import cache_manager
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class ActionStatus(str, Enum):
    """Action execution status"""
    PENDING = "pending"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalStatus(str, Enum):
    """Approval status"""
    PENDING = "pending"
    AUTO_APPROVED = "auto_approved"
    MANUAL_APPROVED = "manual_approved"
    REJECTED = "rejected"


@dataclass
class ActionExecution:
    """Represents an action execution request"""
    id: str
    tenant_id: str
    action: ParsedAction
    prediction_id: Optional[str] = None
    llm_response_id: Optional[str] = None
    status: ActionStatus = ActionStatus.PENDING
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    impact_assessment: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.impact_assessment is None:
            self.impact_assessment = {}
        if self.created_at is None:
            self.created_at = datetime.now()


class SafeActionEngine:
    """
    Safe Action Engine - Orchestrates automated action execution with comprehensive safety controls.
    """

    def __init__(self):
        self.supabase = get_supabase_client()
        self.cache_manager = cache_manager

    async def process_actions_from_llm_response(
        self,
        tenant_id: str,
        llm_response: str,
        prediction_id: Optional[str] = None,
        llm_response_id: Optional[str] = None
    ) -> List[ActionExecution]:
        """
        Process actions from LLM response with full safety pipeline.

        Args:
            tenant_id: Tenant identifier
            llm_response: Raw LLM response text
            prediction_id: Optional prediction identifier
            llm_response_id: Optional LLM response identifier

        Returns:
            List of action executions (may be pending approval)
        """
        try:
            # Check if automation is enabled for tenant
            tenant_settings = await self._get_tenant_action_settings(tenant_id)
            if not tenant_settings.get('automation_enabled', False):
                logger.info(f"Automation disabled for tenant {tenant_id}")
                return []

            # Parse actions from LLM response
            parsed_actions = action_parser_service.parse_actions_from_response(llm_response, tenant_id)
            if not parsed_actions:
                logger.info(f"No valid actions parsed from LLM response for tenant {tenant_id}")
                return []

            executions = []

            for action in parsed_actions:
                # Check canary deployment (gradual rollout)
                if not await self._should_execute_action(tenant_id, action, tenant_settings):
                    logger.info(f"Action {action.action_type} skipped due to canary controls for tenant {tenant_id}")
                    continue

                # Create execution record
                execution = await self._create_action_execution(
                    tenant_id, action, prediction_id, llm_response_id
                )

                # Perform impact assessment
                execution.impact_assessment = await self._assess_impact(execution)

                # Determine approval requirements
                approval_decision = await self._determine_approval_requirement(execution, tenant_settings)

                if approval_decision['requires_approval']:
                    # Create approval request
                    await self._create_approval_request(execution, approval_decision)
                    execution.approval_status = ApprovalStatus.PENDING
                else:
                    # Auto-approve and queue for execution
                    execution.approval_status = ApprovalStatus.AUTO_APPROVED
                    await self._queue_for_execution(execution)

                executions.append(execution)

                # Log audit event
                await self._log_audit_event(
                    tenant_id, execution.id, 'created',
                    {'action_type': action.action_type, 'auto_approved': not approval_decision['requires_approval']}
                )

            logger.info(f"Processed {len(executions)} actions for tenant {tenant_id}")
            return executions

        except Exception as e:
            logger.error(f"Failed to process actions for tenant {tenant_id}: {e}")
            return []

    async def execute_approved_action(self, execution_id: str) -> bool:
        """
        Execute a previously approved action.

        Args:
            execution_id: Action execution identifier

        Returns:
            True if execution successful
        """
        try:
            # Get execution details
            execution = await self._get_action_execution(execution_id)
            if not execution:
                logger.error(f"Action execution {execution_id} not found")
                return False

            if execution.status != ActionStatus.APPROVED:
                logger.warning(f"Action execution {execution_id} not approved (status: {execution.status})")
                return False

            # Update status to executing
            await self._update_execution_status(execution_id, ActionStatus.EXECUTING)

            # Execute the action
            success = await self._execute_action(execution)

            # Update final status
            final_status = ActionStatus.COMPLETED if success else ActionStatus.FAILED
            await self._update_execution_status(execution_id, final_status, executed_at=datetime.now())

            # Log completion
            await self._log_audit_event(
                execution.tenant_id, execution_id, 'executed' if success else 'failed',
                {'success': success}
            )

            return success

        except Exception as e:
            logger.error(f"Failed to execute action {execution_id}: {e}")
            await self._update_execution_status(execution_id, ActionStatus.FAILED, error_message=str(e))
            return False

    async def approve_action(self, execution_id: str, approved_by: str, notes: str = "") -> bool:
        """
        Manually approve an action for execution.

        Args:
            execution_id: Action execution identifier
            approved_by: User who approved
            notes: Optional approval notes

        Returns:
            True if approved successfully
        """
        try:
            # Update approval status
            await self._update_approval_status(execution_id, ApprovalStatus.MANUAL_APPROVED, approved_by, notes)

            # Update execution status
            await self._update_execution_status(execution_id, ActionStatus.APPROVED)

            # Queue for execution
            execution = await self._get_action_execution(execution_id)
            if execution:
                await self._queue_for_execution(execution)

            # Log approval
            await self._log_audit_event(
                execution.tenant_id if execution else 'unknown', execution_id, 'approved',
                {'approved_by': approved_by, 'notes': notes}
            )

            return True

        except Exception as e:
            logger.error(f"Failed to approve action {execution_id}: {e}")
            return False

    async def reject_action(self, execution_id: str, rejected_by: str, reason: str = "") -> bool:
        """
        Reject an action execution request.

        Args:
            execution_id: Action execution identifier
            rejected_by: User who rejected
            reason: Rejection reason

        Returns:
            True if rejected successfully
        """
        try:
            # Update approval status
            await self._update_approval_status(execution_id, ApprovalStatus.REJECTED, rejected_by, reason)

            # Update execution status
            await self._update_execution_status(execution_id, ActionStatus.CANCELLED)

            # Log rejection
            execution = await self._get_action_execution(execution_id)
            await self._log_audit_event(
                execution.tenant_id if execution else 'unknown', execution_id, 'rejected',
                {'rejected_by': rejected_by, 'reason': reason}
            )

            return True

        except Exception as e:
            logger.error(f"Failed to reject action {execution_id}: {e}")
            return False

    async def rollback_action(self, execution_id: str, rollback_reason: str = "") -> bool:
        """
        Rollback a completed action if supported.

        Args:
            execution_id: Action execution identifier
            rollback_reason: Reason for rollback

        Returns:
            True if rollback successful
        """
        try:
            execution = await self._get_action_execution(execution_id)
            if not execution or execution.status != ActionStatus.COMPLETED:
                return False

            # Check if action supports rollback
            action_def = await self._get_action_definition(execution.action.action_type)
            if not action_def or not action_def.get('rollback_supported', False):
                logger.warning(f"Action {execution.action.action_type} does not support rollback")
                return False

            # Perform rollback
            success = await self._rollback_action(execution)

            # Update status
            await self._update_execution_status(
                execution_id,
                ActionStatus.COMPLETED,  # Keep completed but mark rollback
                rollback_status='completed' if success else 'failed'
            )

            # Log rollback
            await self._log_audit_event(
                execution.tenant_id, execution_id, 'rolled_back',
                {'success': success, 'reason': rollback_reason}
            )

            return success

        except Exception as e:
            logger.error(f"Failed to rollback action {execution_id}: {e}")
            return False

    async def _should_execute_action(self, tenant_id: str, action: ParsedAction, tenant_settings: Dict[str, Any]) -> bool:
        """Determine if action should be executed based on canary controls"""
        try:
            canary_percentage = tenant_settings.get('canary_percentage', 0.0)
            if canary_percentage >= 1.0:
                return True
            if canary_percentage <= 0.0:
                return False

            # Simple hash-based canary logic (deterministic but random-like)
            import hashlib
            hash_input = f"{tenant_id}:{action.action_type}:{datetime.now().date()}"
            hash_value = int(hashlib.md5(hash_input.encode()).hexdigest()[:8], 16)
            should_execute = (hash_value % 100) < (canary_percentage * 100)

            return should_execute

        except Exception as e:
            logger.error(f"Error in canary check: {e}")
            return False

    async def _create_action_execution(
        self, tenant_id: str, action: ParsedAction, prediction_id: Optional[str], llm_response_id: Optional[str]
    ) -> ActionExecution:
        """Create action execution record in database"""
        # Use a proper UUID to satisfy DB constraint (id UUID PRIMARY KEY)
        execution_id = str(uuid4())

        # Normalize prediction_id to UUID or set None if not a valid UUID
        pred_uuid = None
        if prediction_id:
            try:
                pred_uuid = str(UUID(str(prediction_id)))
            except Exception:
                pred_uuid = None

        execution_data = {
            'id': execution_id,
            'tenant_id': tenant_id,
            'prediction_id': pred_uuid,
            'llm_response_id': llm_response_id,
            'action_definition_id': await self._get_action_definition_id(action.action_type),
            'action_type': action.action_type,
            'action_params': action.parameters,
            'execution_status': ActionStatus.PENDING.value,
            'approval_status': ApprovalStatus.PENDING.value,
            'confidence_score': action.confidence,
            'impact_assessment': action.impact_assessment,
            'created_at': datetime.now().isoformat()
        }

        # Insert into database
        table = self.supabase.table('action_executions')
        _ = table.insert(execution_data).execute()

        return ActionExecution(
            id=execution_id,
            tenant_id=tenant_id,
            action=action,
            prediction_id=prediction_id,
            llm_response_id=llm_response_id,
            impact_assessment=action.impact_assessment
        )

    async def _assess_impact(self, execution: ActionExecution) -> Dict[str, Any]:
        """Perform impact assessment for the action"""
        # Basic impact assessment - can be extended with more sophisticated logic
        impact = {
            'risk_level': 'low',
            'estimated_duration': '5 minutes',
            'affected_resources': [],
            'rollback_possible': False
        }

        # Action-specific impact assessment
        if execution.action.action_type == 'update_inventory':
            impact.update({
                'risk_level': 'medium',
                'affected_resources': ['inventory', 'stock_levels'],
                'rollback_possible': True
            })
        elif execution.action.action_type == 'create_task':
            impact.update({
                'risk_level': 'low',
                'affected_resources': ['tasks'],
                'rollback_possible': True
            })

        return impact

    async def _determine_approval_requirement(self, execution: ActionExecution, tenant_settings: Dict[str, Any]) -> Dict[str, Any]:
        """Determine if action requires manual approval"""
        requires_approval = tenant_settings.get('approval_required', True)
        auto_threshold = tenant_settings.get('auto_approval_threshold', 0.9)

        # Auto-approve if confidence is high enough and settings allow
        if not requires_approval and execution.action.confidence >= auto_threshold:
            return {
                'requires_approval': False,
                'reason': f'High confidence ({execution.action.confidence}) and auto-approval enabled'
            }

        # Require approval for high-impact actions
        if execution.impact_assessment.get('risk_level') in ['high', 'critical']:
            return {
                'requires_approval': True,
                'reason': f'High-risk action ({execution.impact_assessment["risk_level"]})'
            }

        return {
            'requires_approval': requires_approval,
            'reason': 'Tenant policy requires approval' if requires_approval else f'Confidence below threshold ({execution.action.confidence} < {auto_threshold})'
        }

    async def _create_approval_request(self, execution: ActionExecution, approval_decision: Dict[str, Any]):
        """Create manual approval request"""
        approval_data = {
            'execution_id': execution.id,
            'tenant_id': execution.tenant_id,
            'action_type': execution.action.action_type,
            'action_description': f"Automated {execution.action.action_type} action",
            'impact_summary': approval_decision['reason'],
            'confidence_score': execution.action.confidence,
            'priority': 'high' if execution.impact_assessment.get('risk_level') == 'high' else 'medium',
            'expires_at': (datetime.now() + timedelta(hours=24)).isoformat()
        }

        table = self.supabase.table('action_approvals')
        table.insert(approval_data).execute()

    async def _queue_for_execution(self, execution: ActionExecution):
        """Queue approved action for execution"""
        # In a real implementation, this would queue to Celery or similar
        # For now, we'll mark as approved and let a worker pick it up
        await self._update_execution_status(execution.id, ActionStatus.APPROVED)

    async def _execute_action(self, execution: ActionExecution) -> bool:
        """Execute the actual action"""
        try:
            # Route to appropriate action handler
            if execution.action.action_type == 'create_task':
                return await self._execute_create_task(execution)
            elif execution.action.action_type == 'send_notification':
                return await self._execute_send_notification(execution)
            elif execution.action.action_type == 'update_inventory':
                return await self._execute_update_inventory(execution)
            elif execution.action.action_type == 'generate_report':
                return await self._execute_generate_report(execution)
            else:
                logger.error(f"Unknown action type: {execution.action.action_type}")
                return False

        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return False

    async def _execute_create_task(self, execution: ActionExecution) -> bool:
        """Execute create_task action"""
        params = execution.action.parameters
        task_data = {
            'titulo': params['titulo'],
            'descripcion': params.get('descripcion', ''),
            'prioridad': params.get('prioridad', 'media'),
            'asignada_a_id': params.get('asignada_a_id')
        }

        # Insert task (simplified - would use actual task service)
        table = self.supabase.table('tareas')
        result = table.insert(task_data).execute()
        return len(result.data) > 0 if result.data else False

    async def _execute_send_notification(self, execution: ActionExecution) -> bool:
        """Execute send_notification action"""
        # Simplified notification sending
        logger.info(f"Sending notification: {execution.action.parameters}")
        return True  # Assume success for now

    async def _execute_update_inventory(self, execution: ActionExecution) -> bool:
        """Execute update_inventory action"""
        # Simplified inventory update
        logger.info(f"Updating inventory: {execution.action.parameters}")
        return True  # Assume success for now

    async def _execute_generate_report(self, execution: ActionExecution) -> bool:
        """Execute generate_report action"""
        # Simplified report generation
        logger.info(f"Generating report: {execution.action.parameters}")
        return True  # Assume success for now

    async def _rollback_action(self, execution: ActionExecution) -> bool:
        """Rollback an action"""
        # Simplified rollback logic
        logger.info(f"Rolling back action: {execution.id}")
        return True

    # Helper methods for database operations
    async def _get_tenant_action_settings(self, tenant_id: str) -> Dict[str, Any]:
        """Get tenant action settings"""
        cache_key = f"tenant_action_settings:{tenant_id}"
        cached = self.cache_manager.get('tenant_settings', cache_key)
        if cached:
            return cached if isinstance(cached, dict) else {}

        table = self.supabase.table('tenant_action_settings')
        result = table.select('*').eq('tenant_id', tenant_id).execute()

        settings = result.data[0] if result.data else {}
        self.cache_manager.set('tenant_settings', cache_key, settings, ttl=300)
        return settings

    async def _get_action_definition(self, action_type: str) -> Optional[Dict[str, Any]]:
        """Get action definition"""
        table = self.supabase.table('action_definitions')
        result = table.select('*').eq('action_type', action_type).execute()
        return result.data[0] if result.data else None

    async def _get_action_definition_id(self, action_type: str) -> Optional[str]:
        """Get action definition ID"""
        action_def = await self._get_action_definition(action_type)
        return action_def['id'] if action_def else None

    async def _get_action_execution(self, execution_id: str) -> Optional[ActionExecution]:
        """Get action execution details"""
        table = self.supabase.table('action_executions')
        result = table.select('*').eq('id', execution_id).execute()

        if not result.data:
            return None

        data = result.data[0]
        return ActionExecution(
            id=data['id'],
            tenant_id=data['tenant_id'],
            action=ParsedAction(
                action_type=data['action_type'],
                parameters=data['action_params'],
                confidence=data.get('confidence_score', 1.0)
            ),
            status=ActionStatus(data['execution_status']),
            approval_status=ApprovalStatus(data['approval_status']),
            impact_assessment=data.get('impact_assessment', {})
        )

    async def _update_execution_status(
        self, execution_id: str, status: ActionStatus,
        executed_at: Optional[datetime] = None, error_message: str = "", rollback_status: str = ""
    ):
        """Update execution status"""
        update_data = {'execution_status': status.value}
        if executed_at:
            update_data['executed_at'] = executed_at.isoformat()
        if error_message:
            update_data['error_message'] = error_message
        if rollback_status:
            update_data['rollback_status'] = rollback_status

        table = self.supabase.table('action_executions')
        table.update(update_data).eq('id', execution_id).execute()

    async def _update_approval_status(self, execution_id: str, status: ApprovalStatus, user_id: str, notes: str):
        """Update approval status"""
        update_data = {
            'status': status.value,
            'decided_by': user_id,
            'decided_at': datetime.now().isoformat(),
            'decision_notes': notes
        }

        table = self.supabase.table('action_approvals')
        table.update(update_data).eq('execution_id', execution_id).execute()

    async def _log_audit_event(self, tenant_id: str, execution_id: str, event_type: str, metadata: Dict[str, Any]):
        """Log audit event"""
        audit_data = {
            'tenant_id': tenant_id,
            'execution_id': execution_id,
            'event_type': event_type,
            'metadata': metadata
        }

        table = self.supabase.table('action_audit_log')
        table.insert(audit_data).execute()


# Global instance
safe_action_engine = SafeActionEngine()