from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import json
import asyncio
from datetime import datetime, timedelta
from fastapi import HTTPException
import redis
import logging

from app.db.supabase_client import get_supabase_client
from app.schemas.tenant_settings import RubroEnum

logger = logging.getLogger(__name__)


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
    condition_config: Dict
    parameters: Dict
    is_active: bool = True
    version: str = "1.0"


class NotificationConfigService:
    def __init__(self):
        self.supabase = get_supabase_client()
        self.redis_client = None  # Inicializar después
        self.memory_cache = {}
    
    async def initialize_redis(self):
        """Inicializar Redis de forma lazy"""
        if not self.redis_client:
            try:
                self.redis_client = redis.Redis(
                    host='localhost', 
                    port=6379, 
                    decode_responses=True,
                    socket_timeout=5
                )
                # Test connection
                await asyncio.get_event_loop().run_in_executor(
                    None, self.redis_client.ping
                )
            except Exception as e:
                logger.warning(f"Redis not available, using memory cache only: {e}")
                self.redis_client = None
    
    async def initialize_business_notifications(
        self, 
        tenant_id: str, 
        rubro: str,
        user_preferences: Optional[Dict] = None
    ) -> Dict:
        """
        Inicializar configuración de notificaciones para un negocio.
        Control total desde FastAPI, sin triggers automáticos.
        """
        try:
            # 1. Validar que el negocio existe
            business_check = self.supabase.table("negocios").select("id").eq("id", tenant_id).execute()
            if not business_check.data:
                raise HTTPException(status_code=404, detail="Negocio no encontrado")
            
            # 2. Verificar si ya tiene configuración
            existing_config = self.supabase.table("business_notification_config").select("*").eq("tenant_id", tenant_id).execute()
            if existing_config.data:
                return {
                    "message": "Configuración ya existe",
                    "config_id": existing_config.data[0]["id"],
                    "rubro": existing_config.data[0]["rubro"]
                }
            
            # 3. Obtener templates base para el rubro
            base_templates = await self.get_rubro_templates(rubro)
            
            # 4. Aplicar preferencias del usuario si existen
            custom_overrides = {}
            if user_preferences:
                custom_overrides = self.validate_and_merge_preferences(base_templates, user_preferences)
            
            # 5. Crear configuración del negocio
            config_data = {
                "tenant_id": tenant_id,
                "rubro": rubro,
                "template_version": "latest",
                "custom_overrides": custom_overrides,
                "is_active": True
            }
            
            # 6. Insertar en transacción controlada
            result = self.supabase.table("business_notification_config").insert(config_data).execute()
            
            if not result.data:
                raise HTTPException(status_code=500, detail="Error al crear configuración")
            
            # 7. Log para auditoría
            await self.log_config_creation(tenant_id, rubro, result.data[0])
            
            # 8. Invalidar cache
            await self.invalidate_cache(f"notification_rules:{tenant_id}")
            
            return {
                "config_id": result.data[0]["id"],
                "rules_count": len(base_templates),
                "rubro": rubro,
                "version": "latest",
                "custom_overrides": custom_overrides
            }
            
        except Exception as e:
            logger.error(f"Failed to initialize notifications for {tenant_id}: {str(e)}")
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=500, detail=f"Error initializing notifications: {str(e)}")
    
    async def get_rubro_templates(self, rubro: str, version: str = "latest") -> List[Dict]:
        """Obtener templates de reglas para un rubro específico"""
        try:
            query = self.supabase.table("notification_rule_templates").select("*").eq("rubro", rubro)
            
            if version == "latest":
                query = query.eq("is_latest", True)
            else:
                query = query.eq("version", version)
            
            result = query.execute()
            
            # Si no hay templates específicos para el rubro, usar 'general'
            if not result.data and rubro != "general":
                logger.info(f"No templates found for rubro '{rubro}', falling back to 'general'")
                return await self.get_rubro_templates("general", version)
            
            return result.data or []
            
        except Exception as e:
            logger.error(f"Error getting templates for rubro {rubro}: {str(e)}")
            return []
    
    async def get_effective_rules(self, tenant_id: str) -> List[NotificationRule]:
        """
        Obtener reglas efectivas combinando templates + overrides.
        Patrón Strategy para diferentes rubros.
        """
        # 1. Buscar en cache primero
        await self.initialize_redis()
        cache_key = f"notification_rules:{tenant_id}"
        cached = await self.get_from_cache(cache_key)
        if cached:
            return [NotificationRule(**rule) for rule in cached]
        
        try:
            # 2. Obtener configuración del negocio
            config = await self.get_business_config(tenant_id)
            if not config:
                logger.warning(f"No notification config found for tenant {tenant_id}")
                return []
            
            # 3. Obtener templates base
            base_templates = await self.get_rubro_templates(
                config["rubro"], 
                version=config["template_version"]
            )
            
            # 4. Aplicar overrides personalizados
            effective_rules = self.merge_templates_with_overrides(
                base_templates, 
                config["custom_overrides"]
            )
            
            # 5. Cache por 1 hora
            rules_data = [rule.__dict__ for rule in effective_rules]
            await self.set_cache(cache_key, rules_data, ttl=3600)
            
            return effective_rules
            
        except Exception as e:
            logger.error(f"Error getting effective rules for {tenant_id}: {str(e)}")
            return []
    
    async def get_business_config(self, tenant_id: str) -> Optional[Dict]:
        """Obtener configuración de notificaciones del negocio"""
        try:
            result = self.supabase.table("business_notification_config").select("*").eq("tenant_id", tenant_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error getting business config for {tenant_id}: {str(e)}")
            return None
    
    def merge_templates_with_overrides(self, templates: List[Dict], overrides: Dict) -> List[NotificationRule]:
        """Combinar templates base con overrides personalizados"""
        effective_rules = []
        
        for template in templates:
            rule_type = template["rule_type"]
            
            # Obtener parámetros base
            base_params = template["default_parameters"]
            condition_config = template["condition_config"]
            
            # Aplicar overrides si existen
            if rule_type in overrides:
                override_data = overrides[rule_type]
                
                # Merge parameters
                if "parameters" in override_data:
                    base_params.update(override_data["parameters"])
                
                # Override is_active
                is_active = override_data.get("is_active", True)
            else:
                is_active = True
            
            rule = NotificationRule(
                rule_type=NotificationRuleType(rule_type),
                condition_config=condition_config,
                parameters=base_params,
                is_active=is_active,
                version=template["version"]
            )
            
            effective_rules.append(rule)
        
        return effective_rules
    
    def validate_and_merge_preferences(self, templates: List[Dict], preferences: Dict) -> Dict:
        """Validar y mergear preferencias del usuario"""
        valid_overrides = {}
        
        template_types = {t["rule_type"] for t in templates}
        
        for rule_type, pref_data in preferences.items():
            if rule_type in template_types:
                valid_overrides[rule_type] = pref_data
            else:
                logger.warning(f"Invalid rule type in preferences: {rule_type}")
        
        return valid_overrides
    
    async def update_rule_override(
        self, 
        tenant_id: str, 
        rule_type: NotificationRuleType, 
        overrides: Dict
    ) -> Dict:
        """Actualizar override de regla específica"""
        try:
            # 1. Obtener configuración actual
            config = await self.get_business_config(tenant_id)
            if not config:
                raise HTTPException(status_code=404, detail="Configuración no encontrada")
            
            # 2. Actualizar overrides
            current_overrides = config["custom_overrides"] or {}
            current_overrides[rule_type.value] = overrides
            
            # 3. Guardar en BD
            result = self.supabase.table("business_notification_config").update({
                "custom_overrides": current_overrides,
                "updated_at": datetime.now().isoformat()
            }).eq("tenant_id", tenant_id).execute()
            
            if not result.data:
                raise HTTPException(status_code=500, detail="Error al actualizar regla")
            
            # 4. Log auditoría
            await self.log_rule_update(tenant_id, rule_type.value, overrides)
            
            # 5. Invalidar cache
            await self.invalidate_cache(f"notification_rules:{tenant_id}")
            
            return result.data[0]
            
        except Exception as e:
            logger.error(f"Error updating rule override: {str(e)}")
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=500, detail=f"Error updating rule: {str(e)}")
    
    async def get_available_rubros(self) -> List[str]:
        """Obtener rubros disponibles"""
        return [rubro.value for rubro in RubroEnum]
    
    # Cache methods
    async def get_from_cache(self, key: str) -> Optional[Any]:
        """Obtener datos del cache (Redis o memoria)"""
        # Memory cache first
        if key in self.memory_cache:
            return self.memory_cache[key]
        
        # Redis cache
        if self.redis_client:
            try:
                cached = await asyncio.get_event_loop().run_in_executor(
                    None, self.redis_client.get, key
                )
                if cached:
                    data = json.loads(cached)
                    self.memory_cache[key] = data  # Populate memory cache
                    return data
            except Exception as e:
                logger.warning(f"Redis cache error: {e}")
        
        return None
    
    async def set_cache(self, key: str, value: Any, ttl: int = 3600):
        """Guardar en cache"""
        # Memory cache
        self.memory_cache[key] = value
        
        # Redis cache
        if self.redis_client:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, self.redis_client.setex, key, ttl, json.dumps(value, default=str)
                )
            except Exception as e:
                logger.warning(f"Redis cache set error: {e}")
    
    async def invalidate_cache(self, key: str):
        """Invalidar cache"""
        # Memory cache
        self.memory_cache.pop(key, None)
        
        # Redis cache
        if self.redis_client:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, self.redis_client.delete, key
                )
            except Exception as e:
                logger.warning(f"Redis cache invalidate error: {e}")
    
    # Logging methods
    async def log_config_creation(self, tenant_id: str, rubro: str, config_data: Dict):
        """Log creación de configuración"""
        try:
            log_data = {
                "tenant_id": tenant_id,
                "action": "create",
                "entity_type": "config",
                "entity_id": config_data["id"],
                "new_values": {"rubro": rubro, "config": config_data}
            }
            self.supabase.table("notification_audit_log").insert(log_data).execute()
        except Exception as e:
            logger.error(f"Error logging config creation: {e}")
    
    async def log_rule_update(self, tenant_id: str, rule_type: str, overrides: Dict):
        """Log actualización de regla"""
        try:
            log_data = {
                "tenant_id": tenant_id,
                "action": "update",
                "entity_type": "rule",
                "new_values": {"rule_type": rule_type, "overrides": overrides}
            }
            self.supabase.table("notification_audit_log").insert(log_data).execute()
        except Exception as e:
            logger.error(f"Error logging rule update: {e}")
