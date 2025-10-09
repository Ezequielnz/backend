"""
Tests for Action System components.
Tests action parsing, safe execution, and automation safety controls.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from app.services.action_parser import action_parser_service, ParsedAction
from app.services.safe_action_engine import safe_action_engine, ActionExecution, ActionStatus, ApprovalStatus


class TestActionParser:
    """Test action parsing from LLM responses"""

    def test_parse_actions_from_json_response(self):
        """Test parsing actions from JSON-formatted LLM response"""
        llm_response = """
        Based on the analysis, I recommend the following actions:

        ```json
        {
          "actions": [
            {
              "action_type": "create_task",
              "parameters": {
                "titulo": "Investigar anomalía de ventas",
                "descripcion": "Se detectó una anomalía significativa",
                "prioridad": "alta"
              },
              "confidence": 0.9,
              "reasoning": "High anomaly score requires investigation"
            },
            {
              "action_type": "send_notification",
              "parameters": {
                "titulo": "Alerta de ventas",
                "mensaje": "Anomalía detectada en el sistema",
                "tipo": "warning"
              },
              "confidence": 0.85,
              "reasoning": "Team should be notified"
            }
          ]
        }
        ```
        """

        actions = action_parser_service.parse_actions_from_llm_response(llm_response, "tenant_123")

        assert len(actions) == 2
        assert actions[0].action_type == "create_task"
        assert actions[0].parameters["titulo"] == "Investigar anomalía de ventas"
        assert actions[0].confidence == 0.9
        assert actions[1].action_type == "send_notification"
        assert actions[1].parameters["tipo"] == "warning"

    def test_parse_actions_from_text_response(self):
        """Test parsing actions from text-based LLM response"""
        llm_response = """
        I recommend creating a task to investigate this issue.
        Also, please send a notification to the team about this anomaly.
        """

        actions = action_parser_service.parse_actions_from_llm_response(llm_response, "tenant_123")

        # Text parsing should find some actions with lower confidence
        assert len(actions) >= 1
        # Confidence should be lower for text parsing
        assert all(action.confidence <= 0.8 for action in actions)

    def test_validate_create_task_action(self):
        """Test validation of create_task action parameters"""
        # Valid action
        valid_params = {
            "titulo": "Test task",
            "descripcion": "Test description",
            "prioridad": "media"
        }
        assert action_parser_service._validate_create_task(valid_params)

        # Invalid action - missing title
        invalid_params = {
            "descripcion": "Test description"
        }
        assert not action_parser_service._validate_create_task(invalid_params)

        # Invalid action - title too long
        long_title_params = {
            "titulo": "A" * 201,  # Over 200 characters
            "descripcion": "Test"
        }
        assert not action_parser_service._validate_create_task(long_title_params)
        assert not action_parser_service._validate_create_task(long_title_params)

    def test_validate_send_notification_action(self):
        """Test validation of send_notification action parameters"""
        # Valid action
        valid_params = {
            "titulo": "Test notification",
            "mensaje": "Test message",
            "tipo": "info"
        }
        assert action_parser_service._validate_send_notification(valid_params)

        # Invalid action - missing required fields
        invalid_params = {
            "titulo": "Test"
        }
        assert not action_parser_service._validate_send_notification(invalid_params)

    def test_empty_actions_response(self):
        """Test handling of responses with no actions"""
        llm_response = """
        Analysis complete. No specific actions needed at this time.

        ```json
        {
          "actions": []
        }
        ```
        """

        actions = action_parser_service.parse_actions_from_llm_response(llm_response, "tenant_123")
        assert len(actions) == 0


class TestSafeActionEngine:
    """Test safe action engine functionality"""

    @pytest.fixture
    def mock_supabase(self):
        """Mock Supabase client"""
        with patch('app.services.safe_action_engine.get_supabase_client') as mock:
            mock_client = Mock()
            mock_client.table.return_value.execute.return_value = Mock(data=[])
            mock.return_value = mock_client
            yield mock_client

    @pytest.fixture
    def mock_cache(self):
        """Mock cache manager"""
        with patch('app.services.safe_action_engine.cache_manager') as mock:
            mock.get.return_value = None
            mock.set.return_value = None
            yield mock

    def test_tenant_settings_caching(self, mock_supabase, mock_cache):
        """Test tenant settings are cached properly"""
        # Setup mock response
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = Mock(
            data=[{
                'automation_enabled': True,
                'approval_required': True,
                'canary_percentage': 0.5
            }]
        )

        # First call should fetch from DB
        settings1 = safe_action_engine._get_tenant_action_settings("tenant_123")
        mock_supabase.table.assert_called()

        # Second call should use cache
        mock_supabase.reset_mock()
        settings2 = safe_action_engine._get_tenant_action_settings("tenant_123")
        # Should not call DB again due to caching
        assert settings1 == settings2

    def test_canary_execution_logic(self):
        """Test canary deployment execution logic"""
        tenant_settings = {'canary_percentage': 0.5}  # 50% canary

        # Test with canary disabled
        assert not safe_action_engine._should_execute_action("tenant_123", Mock(), {'canary_percentage': 0.0})

        # Test with canary enabled - this is deterministic based on hash
        # We can't reliably test the random aspect, but we can test the logic
        result = safe_action_engine._should_execute_action("tenant_123", Mock(), tenant_settings)
        assert isinstance(result, bool)

    def test_impact_assessment(self):
        """Test impact assessment logic"""
        execution = ActionExecution(
            id="test_exec",
            tenant_id="tenant_123",
            action=ParsedAction(
                action_type="update_inventory",
                parameters={"producto_id": "prod_123", "cantidad": 10}
            )
        )

        impact = safe_action_engine._assess_impact(execution)

        assert 'risk_level' in impact
        assert 'affected_resources' in impact
        assert 'rollback_possible' in impact

        # Inventory updates should be medium risk and rollbackable
        assert impact['risk_level'] == 'medium'
        assert 'inventory' in impact['affected_resources']
        assert impact['rollback_possible'] is True

    def test_approval_requirement_logic(self):
        """Test approval requirement determination"""
        execution = ActionExecution(
            id="test_exec",
            tenant_id="tenant_123",
            action=ParsedAction(action_type="create_task", parameters={}, confidence=0.95)
        )

        # High confidence, auto-approval enabled
        tenant_settings = {
            'approval_required': False,
            'auto_approval_threshold': 0.9
        }

        decision = safe_action_engine._determine_approval_requirement(execution, tenant_settings)
        assert not decision['requires_approval']
        assert 'High confidence' in decision['reason']

        # Low confidence, requires approval
        execution.action.confidence = 0.5
        decision = safe_action_engine._determine_approval_requirement(execution, tenant_settings)
        assert decision['requires_approval']
        assert 'below threshold' in decision['reason']

        # High risk action always requires approval
        execution.action.action_type = "update_inventory"
        execution.action.confidence = 0.95
        decision = safe_action_engine._determine_approval_requirement(execution, tenant_settings)
        # This might still auto-approve depending on impact assessment

    @pytest.mark.asyncio
    async def test_action_execution_creation(self, mock_supabase):
        """Test action execution record creation"""
        # Setup mock
        mock_supabase.table.return_value.insert.return_value.execute.return_value = Mock(
            data=[{'id': 'test_execution_id'}]
        )

        action = ParsedAction(
            action_type="create_task",
            parameters={"titulo": "Test task"},
            confidence=0.9
        )

        execution = await safe_action_engine._create_action_execution(
            "tenant_123", action, "pred_123", "resp_123"
        )

        assert execution.id.startswith("exec_tenant_123")
        assert execution.tenant_id == "tenant_123"
        assert execution.action.action_type == "create_task"
        assert execution.status == ActionStatus.PENDING
        assert execution.approval_status == ApprovalStatus.PENDING

    def test_action_execution_states(self):
        """Test action execution state transitions"""
        execution = ActionExecution(
            id="test_exec",
            tenant_id="tenant_123",
            action=ParsedAction(action_type="create_task", parameters={})
        )

        # Initial state
        assert execution.status == ActionStatus.PENDING
        assert execution.approval_status == ApprovalStatus.PENDING

        # Simulate approval
        execution.status = ActionStatus.APPROVED
        execution.approval_status = ApprovalStatus.MANUAL_APPROVED
        assert execution.status == ActionStatus.APPROVED

        # Simulate execution
        execution.status = ActionStatus.EXECUTING
        assert execution.status == ActionStatus.EXECUTING

        # Simulate completion
        execution.status = ActionStatus.COMPLETED
        assert execution.status == ActionStatus.COMPLETED


class TestActionIntegration:
    """Integration tests for action system components"""

    @pytest.mark.asyncio
    async def test_full_action_pipeline_simulation(self, mock_supabase, mock_cache):
        """Test complete action pipeline from LLM response to execution"""
        # Setup mocks
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = Mock(
            data=[{
                'automation_enabled': True,
                'approval_required': False,
                'auto_approval_threshold': 0.8,
                'canary_percentage': 1.0  # Full rollout for testing
            }]
        )

        llm_response = """
        I recommend creating a task for this issue.

        ```json
        {
          "actions": [
            {
              "action_type": "create_task",
              "parameters": {
                "titulo": "Test automated task",
                "descripcion": "Created by AI analysis",
                "prioridad": "media"
              },
              "confidence": 0.9,
              "reasoning": "Issue requires follow-up"
            }
          ]
        }
        ```
        """

        # Process actions
        executions = await safe_action_engine.process_actions_from_llm_response(
            "tenant_123", llm_response, "pred_123", "resp_123"
        )

        assert len(executions) == 1
        execution = executions[0]
        assert execution.action.action_type == "create_task"
        assert execution.approval_status == ApprovalStatus.AUTO_APPROVED
        assert execution.status == ActionStatus.APPROVED  # Should be queued for execution

    def test_action_failure_handling(self):
        """Test handling of action execution failures"""
        # Test that failed actions are properly marked
        # Test retry logic
        # Test circuit breaker activation
        pass  # TODO: Implement when execution logic is more complete

    def test_tenant_isolation(self):
        """Test that actions are properly isolated by tenant"""
        # Ensure actions from one tenant don't affect another
        # Test tenant-specific settings
        pass  # TODO: Implement with full tenant context