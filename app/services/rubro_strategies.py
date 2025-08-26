"""
Estrategias híbridas (Strategy + Composition) para configuración de notificaciones por rubro
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class RubroType(str, Enum):
    RESTAURANTE = "restaurante"
    RETAIL = "retail"
    SERVICIOS = "servicios"
    MANUFACTURA = "manufactura"
    TECNOLOGIA = "tecnologia"
    SALUD = "salud"
    EDUCACION = "educacion"
    GENERAL = "general"


class NotificationRuleStrategy(ABC):
    """Estrategia base para configuración de reglas por rubro"""
    
    @abstractmethod
    def get_default_rules(self) -> List[Dict[str, Any]]:
        """Obtener reglas por defecto para el rubro"""
        pass
    
    @abstractmethod
    def get_priority_weights(self) -> Dict[str, float]:
        """Obtener pesos de prioridad para diferentes tipos de reglas"""
        pass
    
    @abstractmethod
    def customize_rule_parameters(self, rule_type: str, base_params: Dict) -> Dict:
        """Personalizar parámetros de regla según el rubro"""
        pass


class RestauranteStrategy(NotificationRuleStrategy):
    """Estrategia específica para restaurantes"""
    
    def get_default_rules(self) -> List[Dict[str, Any]]:
        return [
            {
                "rule_type": "ingredient_stock",
                "condition_config": {
                    "threshold_type": "percentage",
                    "comparison": "less_than",
                    "check_frequency": "daily"
                },
                "default_parameters": {
                    "threshold": 20.0,
                    "critical_threshold": 5.0,
                    "notification_channels": ["email", "app"],
                    "severity": "high"
                },
                "version": "1.0",
                "is_latest": True
            },
            {
                "rule_type": "sales_drop",
                "condition_config": {
                    "threshold_type": "percentage",
                    "comparison": "less_than",
                    "period": "daily",
                    "baseline": "previous_week_average"
                },
                "default_parameters": {
                    "threshold": 30.0,
                    "consecutive_days": 2,
                    "notification_channels": ["email", "app"],
                    "severity": "medium"
                },
                "version": "1.0",
                "is_latest": True
            },
            {
                "rule_type": "seasonal_alert",
                "condition_config": {
                    "threshold_type": "calendar",
                    "check_frequency": "weekly"
                },
                "default_parameters": {
                    "peak_seasons": ["diciembre", "febrero", "julio"],
                    "preparation_days": 14,
                    "notification_channels": ["email"],
                    "severity": "low"
                },
                "version": "1.0",
                "is_latest": True
            }
        ]
    
    def get_priority_weights(self) -> Dict[str, float]:
        return {
            "ingredient_stock": 1.0,
            "sales_drop": 0.8,
            "seasonal_alert": 0.4,
            "high_expenses": 0.6,
            "no_purchases": 0.3
        }
    
    def customize_rule_parameters(self, rule_type: str, base_params: Dict) -> Dict:
        """Personalizar parámetros específicos para restaurantes"""
        customized = base_params.copy()
        
        if rule_type == "ingredient_stock":
            # Restaurantes necesitan alertas más tempranas para ingredientes
            customized["threshold"] = min(customized.get("threshold", 20), 25)
            customized["critical_threshold"] = 5.0
        
        elif rule_type == "sales_drop":
            # Restaurantes son más sensibles a caídas de ventas diarias
            customized["consecutive_days"] = 1
            customized["threshold"] = min(customized.get("threshold", 30), 25)
        
        return customized


class RetailStrategy(NotificationRuleStrategy):
    """Estrategia específica para retail"""
    
    def get_default_rules(self) -> List[Dict[str, Any]]:
        return [
            {
                "rule_type": "low_stock",
                "condition_config": {
                    "threshold_type": "units",
                    "comparison": "less_than",
                    "check_frequency": "daily"
                },
                "default_parameters": {
                    "threshold": 10,
                    "critical_threshold": 2,
                    "notification_channels": ["email", "app"],
                    "severity": "high"
                },
                "version": "1.0",
                "is_latest": True
            },
            {
                "rule_type": "sales_drop",
                "condition_config": {
                    "threshold_type": "percentage",
                    "comparison": "less_than",
                    "period": "weekly",
                    "baseline": "previous_month_average"
                },
                "default_parameters": {
                    "threshold": 20.0,
                    "consecutive_periods": 2,
                    "notification_channels": ["email", "app"],
                    "severity": "medium"
                },
                "version": "1.0",
                "is_latest": True
            },
            {
                "rule_type": "seasonal_alert",
                "condition_config": {
                    "threshold_type": "calendar",
                    "check_frequency": "monthly"
                },
                "default_parameters": {
                    "peak_seasons": ["noviembre", "diciembre", "enero", "marzo"],
                    "preparation_days": 30,
                    "notification_channels": ["email"],
                    "severity": "low"
                },
                "version": "1.0",
                "is_latest": True
            }
        ]
    
    def get_priority_weights(self) -> Dict[str, float]:
        return {
            "low_stock": 1.0,
            "sales_drop": 0.7,
            "seasonal_alert": 0.5,
            "high_expenses": 0.4,
            "no_purchases": 0.6
        }
    
    def customize_rule_parameters(self, rule_type: str, base_params: Dict) -> Dict:
        customized = base_params.copy()
        
        if rule_type == "low_stock":
            # Retail puede manejar stocks más bajos
            customized["threshold"] = max(customized.get("threshold", 10), 5)
        
        elif rule_type == "sales_drop":
            # Retail analiza tendencias semanales
            customized["period"] = "weekly"
            customized["consecutive_periods"] = 2
        
        return customized


class ServiciosStrategy(NotificationRuleStrategy):
    """Estrategia específica para servicios"""
    
    def get_default_rules(self) -> List[Dict[str, Any]]:
        return [
            {
                "rule_type": "no_purchases",
                "condition_config": {
                    "threshold_type": "days",
                    "comparison": "greater_than",
                    "check_frequency": "daily"
                },
                "default_parameters": {
                    "threshold": 7,
                    "critical_threshold": 14,
                    "notification_channels": ["email", "app"],
                    "severity": "medium"
                },
                "version": "1.0",
                "is_latest": True
            },
            {
                "rule_type": "high_expenses",
                "condition_config": {
                    "threshold_type": "percentage",
                    "comparison": "greater_than",
                    "period": "monthly",
                    "baseline": "budget"
                },
                "default_parameters": {
                    "threshold": 110.0,
                    "critical_threshold": 130.0,
                    "notification_channels": ["email"],
                    "severity": "high"
                },
                "version": "1.0",
                "is_latest": True
            },
            {
                "rule_type": "sales_drop",
                "condition_config": {
                    "threshold_type": "percentage",
                    "comparison": "less_than",
                    "period": "monthly",
                    "baseline": "previous_quarter_average"
                },
                "default_parameters": {
                    "threshold": 15.0,
                    "consecutive_periods": 2,
                    "notification_channels": ["email", "app"],
                    "severity": "medium"
                },
                "version": "1.0",
                "is_latest": True
            }
        ]
    
    def get_priority_weights(self) -> Dict[str, float]:
        return {
            "no_purchases": 0.9,
            "high_expenses": 1.0,
            "sales_drop": 0.6,
            "seasonal_alert": 0.3,
            "low_stock": 0.1
        }
    
    def customize_rule_parameters(self, rule_type: str, base_params: Dict) -> Dict:
        customized = base_params.copy()
        
        if rule_type == "no_purchases":
            # Servicios pueden tener períodos más largos sin ventas
            customized["threshold"] = max(customized.get("threshold", 7), 10)
        
        elif rule_type == "high_expenses":
            # Servicios son más sensibles a gastos altos
            customized["threshold"] = min(customized.get("threshold", 110), 105)
        
        return customized


class GeneralStrategy(NotificationRuleStrategy):
    """Estrategia general para rubros no específicos"""
    
    def get_default_rules(self) -> List[Dict[str, Any]]:
        return [
            {
                "rule_type": "sales_drop",
                "condition_config": {
                    "threshold_type": "percentage",
                    "comparison": "less_than",
                    "period": "weekly",
                    "baseline": "previous_month_average"
                },
                "default_parameters": {
                    "threshold": 25.0,
                    "consecutive_periods": 2,
                    "notification_channels": ["email", "app"],
                    "severity": "medium"
                },
                "version": "1.0",
                "is_latest": True
            },
            {
                "rule_type": "high_expenses",
                "condition_config": {
                    "threshold_type": "percentage",
                    "comparison": "greater_than",
                    "period": "monthly",
                    "baseline": "average"
                },
                "default_parameters": {
                    "threshold": 120.0,
                    "notification_channels": ["email"],
                    "severity": "medium"
                },
                "version": "1.0",
                "is_latest": True
            },
            {
                "rule_type": "no_purchases",
                "condition_config": {
                    "threshold_type": "days",
                    "comparison": "greater_than",
                    "check_frequency": "daily"
                },
                "default_parameters": {
                    "threshold": 5,
                    "critical_threshold": 10,
                    "notification_channels": ["email", "app"],
                    "severity": "low"
                },
                "version": "1.0",
                "is_latest": True
            }
        ]
    
    def get_priority_weights(self) -> Dict[str, float]:
        return {
            "sales_drop": 0.8,
            "high_expenses": 0.7,
            "no_purchases": 0.5,
            "low_stock": 0.6,
            "seasonal_alert": 0.4
        }
    
    def customize_rule_parameters(self, rule_type: str, base_params: Dict) -> Dict:
        # Estrategia general no personaliza parámetros
        return base_params.copy()


class RubroStrategyFactory:
    """Factory para crear estrategias según el rubro"""
    
    _strategies = {
        RubroType.RESTAURANTE: RestauranteStrategy,
        RubroType.RETAIL: RetailStrategy,
        RubroType.SERVICIOS: ServiciosStrategy,
        RubroType.GENERAL: GeneralStrategy,
        # Otros rubros usan estrategia general por defecto
        RubroType.MANUFACTURA: GeneralStrategy,
        RubroType.TECNOLOGIA: ServiciosStrategy,  # Similar a servicios
        RubroType.SALUD: ServiciosStrategy,       # Similar a servicios
        RubroType.EDUCACION: ServiciosStrategy,   # Similar a servicios
    }
    
    @classmethod
    def create_strategy(cls, rubro: str) -> NotificationRuleStrategy:
        """Crear estrategia para un rubro específico"""
        try:
            rubro_type = RubroType(rubro.lower())
        except ValueError:
            logger.warning(f"Rubro desconocido '{rubro}', usando estrategia general")
            rubro_type = RubroType.GENERAL
        
        strategy_class = cls._strategies.get(rubro_type, GeneralStrategy)
        return strategy_class()
    
    @classmethod
    def get_available_rubros(cls) -> List[str]:
        """Obtener lista de rubros disponibles"""
        return [rubro.value for rubro in RubroType]


class RubroCompositionService:
    """Servicio de composición que combina estrategias con configuraciones específicas"""
    
    def __init__(self, rubro: str):
        self.rubro = rubro
        self.strategy = RubroStrategyFactory.create_strategy(rubro)
        self.logger = logging.getLogger(f"{__name__}.{rubro}")
    
    def get_initial_configuration(self, user_preferences: Optional[Dict] = None) -> Dict[str, Any]:
        """Obtener configuración inicial completa para el rubro"""
        # 1. Obtener reglas base de la estrategia
        base_rules = self.strategy.get_default_rules()
        
        # 2. Obtener pesos de prioridad
        priority_weights = self.strategy.get_priority_weights()
        
        # 3. Aplicar personalizaciones de la estrategia
        customized_rules = []
        for rule in base_rules:
            rule_type = rule["rule_type"]
            customized_params = self.strategy.customize_rule_parameters(
                rule_type, 
                rule["default_parameters"]
            )
            
            customized_rule = rule.copy()
            customized_rule["default_parameters"] = customized_params
            customized_rule["priority_weight"] = priority_weights.get(rule_type, 0.5)
            customized_rules.append(customized_rule)
        
        # 4. Aplicar preferencias del usuario si existen
        if user_preferences:
            customized_rules = self._apply_user_preferences(customized_rules, user_preferences)
        
        return {
            "rubro": self.rubro,
            "strategy_type": self.strategy.__class__.__name__,
            "rules": customized_rules,
            "priority_weights": priority_weights,
            "total_rules": len(customized_rules),
            "active_rules": len([r for r in customized_rules if r.get("is_active", True)])
        }
    
    def _apply_user_preferences(self, rules: List[Dict], preferences: Dict) -> List[Dict]:
        """Aplicar preferencias del usuario a las reglas"""
        modified_rules = []
        
        for rule in rules:
            rule_type = rule["rule_type"]
            
            if rule_type in preferences:
                user_pref = preferences[rule_type]
                modified_rule = rule.copy()
                
                # Aplicar overrides de parámetros
                if "parameters" in user_pref:
                    modified_rule["default_parameters"].update(user_pref["parameters"])
                
                # Aplicar estado activo/inactivo
                if "is_active" in user_pref:
                    modified_rule["is_active"] = user_pref["is_active"]
                
                # Aplicar canales de notificación personalizados
                if "notification_channels" in user_pref:
                    modified_rule["default_parameters"]["notification_channels"] = user_pref["notification_channels"]
                
                modified_rules.append(modified_rule)
            else:
                modified_rules.append(rule)
        
        return modified_rules
    
    def validate_rule_override(self, rule_type: str, override_data: Dict) -> Dict:
        """Validar y ajustar override según la estrategia del rubro"""
        # 1. Obtener parámetros base para validación
        base_rules = self.strategy.get_default_rules()
        base_rule = next((r for r in base_rules if r["rule_type"] == rule_type), None)
        
        if not base_rule:
            raise ValueError(f"Tipo de regla '{rule_type}' no válido para rubro '{self.rubro}'")
        
        # 2. Validar parámetros según la estrategia
        validated_override = override_data.copy()
        
        if "parameters" in validated_override:
            # Aplicar personalización de la estrategia a los nuevos parámetros
            base_params = base_rule["default_parameters"].copy()
            base_params.update(validated_override["parameters"])
            
            customized_params = self.strategy.customize_rule_parameters(rule_type, base_params)
            validated_override["parameters"] = customized_params
        
        return validated_override
    
    def apply_rubro_transformations(self, rule_type: str, base_params: Dict) -> Dict:
        """Aplicar transformaciones específicas del rubro a los parámetros base"""
        return self.strategy.customize_rule_parameters(rule_type, base_params)
