"""
Action Parser Service - Extracts and validates structured actions from LLM responses.
Parses LLM outputs to identify recommended actions and their parameters.
"""
import json
import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class ActionType(str, Enum):
    """Supported action types"""
    CREATE_TASK = "create_task"
    SEND_NOTIFICATION = "send_notification"
    UPDATE_INVENTORY = "update_inventory"
    GENERATE_REPORT = "generate_report"


class ParsedAction:
    """Represents a parsed action from LLM response"""

    def __init__(self, action_type: str, parameters: Dict[str, Any], confidence: float = 1.0,
                reasoning: str = "", impact_assessment: Optional[Dict[str, Any]] = None):
        self.action_type = action_type
        self.parameters = parameters
        self.confidence = confidence
        self.reasoning = reasoning
        self.impact_assessment = impact_assessment or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "parameters": self.parameters,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "impact_assessment": self.impact_assessment
        }


class ActionParserService:
    """
    Service for parsing structured actions from LLM responses.
    Supports multiple parsing strategies and validation.
    """

    def __init__(self):
        # Use canonical string keys to avoid Enum/string mismatches and support variant inputs
        self.supported_actions = {
            "create_task": self._validate_create_task,
            "send_notification": self._validate_send_notification,
            "update_inventory": self._validate_update_inventory,
            "generate_report": self._validate_generate_report,
        }

    def _normalize_action_type(self, atype: Optional[str]) -> Optional[str]:
        """
        Normalize action type variants to canonical keys expected by the engine.

        Accepts variants like:
          - create_task / createtask / create-task
          - send_notification / sendnotification / send-notification
          - update_inventory / updateinventory / update-inventory
          - generate_report / generatereport / generate-report
        """
        if not atype:
            return None
        s = atype.strip().lower().replace("-", "_").replace(" ", "_")
        variants = {
            "create_task": "create_task",
            "createtask": "create_task",
            "create-task": "create_task",
            "send_notification": "send_notification",
            "sendnotification": "send_notification",
            "send-notification": "send_notification",
            "update_inventory": "update_inventory",
            "updateinventory": "update_inventory",
            "update-inventory": "update_inventory",
            "generate_report": "generate_report",
            "generatereport": "generate_report",
            "generate-report": "generate_report",
        }
        # Return mapped canonical or the original if already canonical
        if s in variants:
            return variants[s]
        if s in variants.values():
            return s
        return None

    def parse_actions_from_response(self, llm_response: str, tenant_id: str) -> List[ParsedAction]:
        """
        Parse actions from LLM response text.

        Args:
            llm_response: Raw LLM response text
            tenant_id: Tenant identifier for context

        Returns:
            List of parsed and validated actions
        """
        try:
            # Try multiple parsing strategies
            actions = []

            # Strategy 1: JSON block extraction
            json_actions = self._parse_json_actions(llm_response)
            actions.extend(json_actions)

            # Strategy 2: Structured text parsing (fallback)
            if not actions:
                text_actions = self._parse_text_actions(llm_response)
                actions.extend(text_actions)

            # Validate and filter actions
            valid_actions = []
            for action in actions:
                if self._validate_action(action, tenant_id):
                    valid_actions.append(action)
                else:
                    logger.warning(f"Invalid action filtered out: {action.action_type}")

            logger.info(f"Parsed {len(valid_actions)} valid actions from LLM response for tenant {tenant_id}")
            return valid_actions

        except Exception as e:
            logger.error(f"Failed to parse actions from LLM response: {e}")
            return []

    def _parse_json_actions(self, response: str) -> List[ParsedAction]:
        """Parse actions from JSON blocks in the response"""
        actions = []

        # Look for JSON code blocks or action sections
        json_patterns = [
            r'```json\s*(\{.*?\})\s*```',  # ```json {...} ```
            r'```\s*(\{.*?\})\s*```',      # ```{...}```
            r'"actions":\s*(\[.*?\])',     # "actions": [...]
            r'"recommended_actions":\s*(\[.*?\])',  # "recommended_actions": [...]
        ]

        for pattern in json_patterns:
            matches = re.findall(pattern, response, re.DOTALL | re.IGNORECASE)
            for match in matches:
                try:
                    data = json.loads(match)
                    if isinstance(data, list):
                        # Array of actions
                        for action_data in data:
                            action = self._parse_single_action_json(action_data)
                            if action:
                                actions.append(action)
                    elif isinstance(data, dict):
                        # Single action or actions object
                        if 'actions' in data and isinstance(data['actions'], list):
                            for action_data in data['actions']:
                                action = self._parse_single_action_json(action_data)
                                if action:
                                    actions.append(action)
                        else:
                            # Single action
                            action = self._parse_single_action_json(data)
                            if action:
                                actions.append(action)
                except json.JSONDecodeError:
                    continue

        return actions

    def _parse_single_action_json(self, action_data: Dict[str, Any]) -> Optional[ParsedAction]:
        """Parse a single action from JSON data"""
        try:
            action_type_raw = action_data.get('action_type') or action_data.get('type')
            action_type = self._normalize_action_type(str(action_type_raw) if action_type_raw else "")
            if not action_type:
                return None

            parameters = action_data.get('parameters', action_data.get('params', {}))
            confidence = action_data.get('confidence', 1.0)
            reasoning = action_data.get('reasoning', action_data.get('explanation', ''))
            impact = action_data.get('impact_assessment', {})

            return ParsedAction(
                action_type=action_type,
                parameters=parameters,
                confidence=float(confidence),
                reasoning=reasoning,
                impact_assessment=impact
            )
        except Exception as e:
            logger.warning(f"Failed to parse single action JSON: {e}")
            return None

    def _parse_text_actions(self, response: str) -> List[ParsedAction]:
        """Parse actions from structured text (fallback method)"""
        actions = []

        # Look for action recommendations in text
        action_patterns = {
            'create_task': [
                r'recommend.*(?:creating?|making)\s+a?\s*task.*?["\']([^"\']+)["\']',
                r'suggest.*task.*?["\']([^"\']+)["\']',
                r'should create.*?task.*?["\']([^"\']+)["\']'
            ],
            'send_notification': [
                r'recommend.*(?:sending?|notifying).*?["\']([^"\']+)["\']',
                r'should send.*?notification.*?["\']([^"\']+)["\']',
                r'notify.*?["\']([^"\']+)["\']'
            ],
            'update_inventory': [
                r'recommend.*(?:updating?|adjusting).*?inventory',
                r'should update.*?inventory',
                r'adjust.*?stock'
            ],
            'generate_report': [
                r'recommend.*(?:generating?|creating).*?report',
                r'should generate.*?report',
                r'create.*?report'
            ]
        }

        for action_type, patterns in action_patterns.items():
            for pattern in patterns:
                matches = re.findall(pattern, response, re.IGNORECASE)
                if matches:
                    # Create basic action from text match
                    parameters = {}
                    if action_type == 'create_task' and matches:
                        parameters['titulo'] = matches[0][:200]  # Limit title length
                        parameters['descripcion'] = f"Automatically created based on AI analysis: {matches[0]}"

                    action = ParsedAction(
                        action_type=action_type,
                        parameters=parameters,
                        confidence=0.7,  # Lower confidence for text parsing
                        reasoning=f"Extracted from text analysis: {matches[0] if matches else 'General recommendation'}"
                    )
                    actions.append(action)
                    break  # Only one action per type from text

        return actions

    def _validate_action(self, action: ParsedAction, tenant_id: str) -> bool:
        """
        Validate a parsed action against business rules and tenant settings.

        Args:
            action: Parsed action to validate
            tenant_id: Tenant identifier

        Returns:
            True if action is valid
        """
        try:
            # Normalize to canonical key and check support
            canonical = self._normalize_action_type(action.action_type)
            if not canonical or canonical not in self.supported_actions:
                logger.warning(f"Unsupported action type: {action.action_type}")
                return False

            # Validate action parameters using type-specific validator
            validator = self.supported_actions[canonical]
            return bool(validator(action.parameters))

        except Exception as e:
            logger.error(f"Action validation failed: {e}")
            return False

    def _validate_create_task(self, params: Dict[str, Any]) -> bool:
        """Validate create_task action parameters"""
        if not params.get('titulo'):
            return False
        if len(params.get('titulo', '')) > 200:
            return False
        if params.get('descripcion') and len(params['descripcion']) > 1000:
            return False
        if params.get('prioridad') and params['prioridad'] not in ['baja', 'media', 'alta', 'urgente']:
            return False
        return True

    def _validate_send_notification(self, params: Dict[str, Any]) -> bool:
        """Validate send_notification action parameters"""
        if not params.get('titulo') or not params.get('mensaje'):
            return False
        if len(params.get('titulo', '')) > 200 or len(params.get('mensaje', '')) > 1000:
            return False
        if params.get('tipo') and params['tipo'] not in ['info', 'warning', 'error', 'success']:
            return False
        return True

    def _validate_update_inventory(self, params: Dict[str, Any]) -> bool:
        """Validate update_inventory action parameters"""
        if not params.get('producto_id') or params.get('cantidad') is None:
            return False
        if not isinstance(params['cantidad'], (int, float)):
            return False
        if params.get('tipo_ajuste') and params['tipo_ajuste'] not in ['incremento', 'decremento', 'set']:
            return False
        return True

    def _validate_generate_report(self, params: Dict[str, Any]) -> bool:
        """Validate generate_report action parameters"""
        if not params.get('tipo_reporte'):
            return False
        if params['tipo_reporte'] not in ['ventas', 'inventario', 'finanzas', 'clientes']:
            return False
        return True

    def get_supported_action_types(self) -> List[str]:
        """Get list of supported action types"""
        return list(self.supported_actions.keys())


# Global instance
action_parser_service = ActionParserService()