from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from fastapi import HTTPException
import logging
from typing import cast, Protocol, Callable
from supabase.client import Client

from app.db.supabase_client import get_supabase_client, TableQueryProto
from app.core.cache_manager import cache_manager, CacheManager
from app.core.cache_decorators import cache_notification_rules, invalidate_on_update
from app.services.rubro_strategies import RubroCompositionService, RubroStrategyFactory

logger = logging.getLogger(__name__)


class _RubroCompositionProto(Protocol):
    def get_initial_configuration(self, user_preferences: dict[str, object] | None = None) -> dict[str, object]:
        ...

    def apply_rubro_transformations(self, rule_type: str, base_params: dict[str, object]) -> dict[str, object]:
        ...

    def validate_rule_override(self, rule_type: str, override_data: dict[str, object]) -> dict[str, object]:
        ...


class NotificationRuleType(str, Enum):
    SALES_DROP = "sales_drop"
    LOW_STOCK = "low_stock"
    NO_PURCHASES = "no_purchases"
    SEASONAL_ALERT = "seasonal_alert"
    INGREDIENT_STOCK = "ingredient_stock"
    HIGH_EXPENSES = "high_expenses"


@dataclass
class NotificationRule:
    rule_type: NotificationRuleType
    condition_config: dict[str, object]
    parameters: dict[str, object]
    is_active: bool = True
    version: str = "1.0"


class NotificationConfigService:
    def __init__(self):
        super().__init__()
        self.supabase: Client = get_supabase_client()
        self.cache_manager: CacheManager = cache_manager
        self.logger: logging.Logger = logging.getLogger(__name__)
    
    def _table(self, name: str) -> TableQueryProto:
        """Typed supabase table builder to reduce 'Unknown' types."""
        table_fn = cast(Callable[[str], object], getattr(self.supabase, "table"))
        return cast(TableQueryProto, table_fn(name))
    
    async def initialize_business_notifications(
        self, 
        tenant_id: str, 
        rubro: str,
        user_preferences: dict[str, object] | None = None
    ) -> dict[str, object]:
        """
        Inicializar configuración de notificaciones usando estrategia híbrida por rubro.
        Integra Strategy + Composition pattern con cache automático.
        """
        try:
            # 1. Validar que el negocio existe
            table_neg = self._table("negocios")
            resp_neg = table_neg.select("id").eq("id", tenant_id).execute()
            neg_data = resp_neg.data
            business_rows: list[dict[str, object]] = neg_data if neg_data is not None else []
            if not business_rows:
                raise HTTPException(status_code=404, detail="Negocio no encontrado")
            
            # 2. Verificar si ya tiene configuración
            table_cfg_q = self._table("business_notification_config")
            cfg_resp = table_cfg_q.select("*").eq("tenant_id", tenant_id).execute()
            cfg_data = cfg_resp.data
            existing_rows: list[dict[str, object]] = cfg_data if cfg_data is not None else []
            if existing_rows:
                return {
                    "message": "Configuración ya existe",
                    "config_id": existing_rows[0]["id"],
                    "rubro": existing_rows[0]["rubro"]
                }
            
            # 3. Usar estrategia híbrida para obtener configuración inicial
            composition_service: _RubroCompositionProto = cast(_RubroCompositionProto, RubroCompositionService(rubro))
            initial_config = composition_service.get_initial_configuration(user_preferences)
            
            # 4. Crear configuración del negocio
            config_data: dict[str, object] = {
                "tenant_id": tenant_id,
                "rubro": rubro,
                "template_version": "latest",
                "custom_overrides": {},
                "strategy_config": {
                    "strategy_type": initial_config["strategy_type"],
                    "priority_weights": initial_config["priority_weights"]
                },
                "is_active": True
            }
            
            # 5. Insertar configuración
            table_cfg = self._table("business_notification_config")
            ins_resp = table_cfg.insert(config_data).execute()
            ins_data = ins_resp.data
            inserted: list[dict[str, object]] = ins_data if ins_data is not None else []
            if not inserted:
                raise HTTPException(status_code=500, detail="Error al crear configuración")
            
            # 6. Insertar reglas iniciales en templates (si no existen)
            await self._ensure_rubro_templates(
                rubro,
                cast(list[dict[str, object]], initial_config["rules"])
            )
            
            # 7. Log para auditoría
            await self.log_config_creation(tenant_id, rubro, inserted[0])
            
            # 8. Invalidar cache
            self.cache_manager.delete("notification_rules", f"rules_{tenant_id}")
            
            return {
                "config_id": inserted[0]["id"],
                "rules_count": initial_config["total_rules"],
                "active_rules": initial_config["active_rules"],
                "rubro": rubro,
                "strategy_type": initial_config["strategy_type"],
                "version": "latest"
            }
            
        except Exception as e:
            self.logger.error(f"Failed to initialize notifications for {tenant_id}: {str(e)}")
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=500, detail=f"Error initializing notifications: {str(e)}")
    
    
    async def get_rubro_templates(self, rubro: str, version: str = "latest") -> list[dict[str, object]]:
        """Obtener templates de reglas para un rubro específico"""
        try:
            builder = self._table("notification_rule_templates")
            q = builder.select("*").eq("rubro", rubro)
            if version == "latest":
                resp = q.eq("is_latest", True).execute()
            else:
                resp = q.eq("version", version).execute()
            data = resp.data
            rows: list[dict[str, object]] = data if data is not None else []
            
            # Si no hay templates específicos para el rubro, usar 'general'
            if not rows and rubro != "general":
                logger.info(f"No templates found for rubro '{rubro}', falling back to 'general'")
                return await self.get_rubro_templates("general", version)
            
            return rows
        
        except Exception as e:
            logger.error(f"Error getting templates for rubro {rubro}: {str(e)}")
            return []
    
    async def _ensure_rubro_templates(self, rubro: str, rules: list[dict[str, object]]) -> None:
        """Asegurar que existen templates para el rubro específico en la BD"""
        try:
            # Verificar si ya existen templates para este rubro
            existing_templates = await self.get_rubro_templates(rubro)
            
            if existing_templates:
                self.logger.info(f"Templates already exist for rubro '{rubro}', skipping creation")
                return
            
            # Crear templates para el rubro basados en las reglas de la estrategia
            template_data: list[dict[str, object]] = []
            
            for rule in rules:
                template: dict[str, object] = {
                    "rubro": rubro,
                    "rule_type": rule["rule_type"],
                    "condition_config": rule["condition_config"],
                    "default_parameters": rule["default_parameters"],
                    "version": "1.0",
                    "is_latest": True,
                    "description": rule.get("description", f"Template for {rule['rule_type']} in {rubro}"),
                    "created_at": datetime.now().isoformat(),
                    "priority": rule.get("priority", "medium")
                }
                template_data.append(template)
            
            # Insertar templates en la BD
            if template_data:
                table_tpl = self._table("notification_rule_templates")
                tpl_resp = table_tpl.insert(template_data).execute()
                tpl_data = tpl_resp.data
                inserted_templates: list[dict[str, object]] = tpl_data if tpl_data is not None else []
                
                if inserted_templates:
                    self.logger.info(f"Created {len(inserted_templates)} templates for rubro '{rubro}'")
                else:
                    self.logger.warning(f"No templates were created for rubro '{rubro}'")
            
        except Exception as e:
            self.logger.error(f"Error ensuring rubro templates for '{rubro}': {str(e)}")
            # No lanzamos excepción para no interrumpir el flujo principal
            pass
    
    @cache_notification_rules(ttl=3600)
    async def get_effective_rules(self, tenant_id: str) -> list[NotificationRule]:
        """
        Obtener reglas efectivas combinando templates + overrides + cache automático.
        Usa Strategy pattern híbrido por rubro.
        """
        try:
            # 1. Obtener configuración del negocio
            config = await self.get_business_config(tenant_id)
            if not config:
                self.logger.warning(f"No notification config found for tenant {tenant_id}")
                return []
            
            # 2. Obtener templates base usando estrategia del rubro
            rubro_str = cast(str, config["rubro"])  
            template_version = cast(str, config["template_version"])  
            base_templates = await self.get_rubro_templates(
                rubro_str,
                version=template_version
            )
            
            # 3. Aplicar overrides personalizados con estrategia híbrida
            composition_service: _RubroCompositionProto = cast(_RubroCompositionProto, RubroCompositionService(rubro_str))
            effective_rules = self.merge_templates_with_overrides_hybrid(
                base_templates, 
                cast(dict[str, object], config.get("custom_overrides") or {}),
                composition_service
            )
            
            return effective_rules
            
        except Exception as e:
            self.logger.error(f"Error getting effective rules for {tenant_id}: {str(e)}")
            return []
    
    async def get_business_config(self, tenant_id: str) -> dict[str, object] | None:
        """Obtener configuración de notificaciones del negocio"""
        try:
            table_cfg_q = self._table("business_notification_config")
            resp = table_cfg_q.select("*").eq("tenant_id", tenant_id).execute()
            data = resp.data
            rows: list[dict[str, object]] = data if data is not None else []
            return rows[0] if rows else None
        except Exception as e:
            logger.error(f"Error getting business config for {tenant_id}: {str(e)}")
            return None
    
    def merge_templates_with_overrides_hybrid(self, templates: list[dict[str, object]], overrides: dict[str, object], composition_service: _RubroCompositionProto) -> list[NotificationRule]:
        """Combinar templates base con overrides usando estrategia híbrida por rubro"""
        effective_rules: list[NotificationRule] = []
        
        for template in templates:
            rule_type = cast(str, template["rule_type"])
            
            # Obtener parámetros base del template
            base_params = cast(dict[str, object], template["default_parameters"]).copy()
            condition_config = cast(dict[str, object], template["condition_config"]).copy()
            
            # Aplicar transformaciones específicas del rubro usando la estrategia
            rubro_params = composition_service.apply_rubro_transformations(rule_type, base_params)
            
            # Aplicar overrides personalizados si existen
            if rule_type in overrides:
                override_data = cast(dict[str, object], overrides[rule_type])
                
                # Validar override usando la estrategia del rubro
                validated_override = composition_service.validate_rule_override(rule_type, override_data)
                
                # Merge parameters con validación
                if "parameters" in validated_override:
                    params_override = cast(dict[str, object], validated_override["parameters"])
                    rubro_params.update(params_override)
                
                # Override condition_config si está presente
                if "condition_config" in validated_override:
                    cond_override = cast(dict[str, object], validated_override["condition_config"])
                    condition_config.update(cond_override)
                
                # Override is_active
                is_active = cast(bool, validated_override.get("is_active", True))
            else:
                is_active = True
            
            rule = NotificationRule(
                rule_type=NotificationRuleType(rule_type),
                condition_config=condition_config,
                parameters=rubro_params,
                is_active=is_active,
                version=cast(str, template["version"])
            )
            
            effective_rules.append(rule)
        
        return effective_rules
    
    def merge_templates_with_overrides(self, templates: list[dict[str, object]], overrides: dict[str, object]) -> list[NotificationRule]:
        """Combinar templates base con overrides personalizados"""
        effective_rules: list[NotificationRule] = []
        
        for template in templates:
            rule_type = cast(str, template["rule_type"])
            
            # Obtener parámetros base
            base_params = cast(dict[str, object], template["default_parameters"]).copy()
            condition_config = cast(dict[str, object], template["condition_config"]).copy()
            
            # Aplicar overrides si existen
            if rule_type in overrides:
                override_data = cast(dict[str, object], overrides[rule_type])
                
                # Merge parameters
                if "parameters" in override_data:
                    params_override = cast(dict[str, object], override_data["parameters"])
                    base_params.update(params_override)
                
                # Override is_active
                is_active = cast(bool, override_data.get("is_active", True))
            else:
                is_active = True
            
            rule = NotificationRule(
                rule_type=NotificationRuleType(rule_type),
                condition_config=condition_config,
                parameters=base_params,
                is_active=is_active,
                version=cast(str, template["version"])
            )
            
            effective_rules.append(rule)
        
        return effective_rules
    
    def validate_and_merge_preferences(self, templates: list[dict[str, object]], preferences: dict[str, object]) -> dict[str, object]:
        """Validar y mergear preferencias del usuario"""
        valid_overrides: dict[str, object] = {}
        
        template_types = {cast(str, t["rule_type"]) for t in templates}
        
        for rule_type, pref_data in preferences.items():
            if rule_type in template_types:
                valid_overrides[rule_type] = pref_data
            else:
                logger.warning(f"Invalid rule type in preferences: {rule_type}")
        
        return valid_overrides
    
    @invalidate_on_update("notification_rules")
    async def update_rule_override(
        self, 
        tenant_id: str, 
        rule_type: NotificationRuleType, 
        overrides: dict[str, object]
    ) -> dict[str, object]:
        """Actualizar override de regla específica con validación por estrategia"""
        try:
            # 1. Obtener configuración actual
            config = await self.get_business_config(tenant_id)
            if not config:
                raise HTTPException(status_code=404, detail="Configuración no encontrada")
            
            # 2. Validar override usando estrategia del rubro
            composition_service: _RubroCompositionProto = cast(_RubroCompositionProto, RubroCompositionService(cast(str, config["rubro"])))
            validated_overrides: dict[str, object] = composition_service.validate_rule_override(
                rule_type.value,
                overrides,
            )
            
            # 3. Actualizar overrides
            current_overrides = cast(dict[str, object], config["custom_overrides"] or {})
            current_overrides[rule_type.value] = validated_overrides
            
            # 4. Guardar en BD
            table_cfg = self._table("business_notification_config")
            upd_resp = table_cfg.update({
                "custom_overrides": current_overrides,
                "updated_at": datetime.now().isoformat()
            }).eq("tenant_id", tenant_id).execute()
            upd_data = upd_resp.data
            updated_rows: list[dict[str, object]] = upd_data if upd_data is not None else []
            
            if not updated_rows:
                raise HTTPException(status_code=500, detail="Error al actualizar regla")
            
            # 5. Log auditoría
            await self.log_rule_update(tenant_id, rule_type.value, validated_overrides)
            
            # 6. Cache se invalida automáticamente por el decorador
            
            return updated_rows[0]
            
        except Exception as e:
            self.logger.error(f"Error updating rule override: {str(e)}")
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=500, detail=f"Error updating rule: {str(e)}")
    
    async def get_available_rubros(self) -> list[str]:
        """Obtener rubros disponibles desde factory de estrategias"""
        return RubroStrategyFactory.get_available_rubros()
    
    # Cache helper methods (using global cache_manager)
    async def get_from_cache(self, namespace: str, key: str) -> object | None:
        """Obtener datos del cache usando cache_manager global"""
        return self.cache_manager.get(namespace, key)
    
    async def set_cache(self, namespace: str, key: str, value: object, ttl: int = 3600):
        """Guardar en cache usando cache_manager global"""
        self.cache_manager.set(namespace, key, value, ttl)
    
    async def invalidate_cache(self, namespace: str, key: str):
        """Invalidar cache usando cache_manager global"""
        self.cache_manager.delete(namespace, key)
    
    # Logging methods
    async def log_config_creation(self, tenant_id: str, rubro: str, config_data: dict[str, object]):
        """Log creación de configuración"""
        try:
            log_data: dict[str, object] = {
                "tenant_id": tenant_id,
                "action": "create",
                "entity_type": "config",
                "entity_id": config_data["id"],
                "new_values": {"rubro": rubro, "config": config_data}
            }
            table_log = self._table("notification_audit_log")
            resp_obj = table_log.insert(log_data).execute()
            _ = resp_obj
        except Exception as e:
            logger.error(f"Error logging config creation: {e}")
    
    async def log_rule_update(self, tenant_id: str, rule_type: str, overrides: dict[str, object]):
        """Log actualización de regla"""
        try:
            log_data: dict[str, object] = {
                "tenant_id": tenant_id,
                "action": "update",
                "entity_type": "rule",
                "new_values": {"rule_type": rule_type, "overrides": overrides}
            }
            table_log = self._table("notification_audit_log")
            resp_obj = table_log.insert(log_data).execute()
            _ = resp_obj
        except Exception as e:
            logger.error(f"Error logging rule update: {e}")
