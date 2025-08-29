"""
Sistema de caché multi-nivel para features ML y reglas de notificación
L1: Memoria local (LRU)
L2: Redis 
L3: Fallback a base de datos
"""
import json
import time
from typing import cast, Protocol, runtime_checkable
from collections.abc import Mapping, Sequence
# datetime y timedelta no se usan actualmente, comentadas para evitar warnings
# from datetime import datetime, timedelta
import redis
import logging
from app.core.config import settings
from supabase.client import create_client

logger = logging.getLogger(__name__)

@runtime_checkable
class SupabaseQuery(Protocol):
    def select(self, columns: str) -> "SupabaseQuery": ...
    def eq(self, column: str, value: object) -> "SupabaseQuery": ...
    def order(self, column: str, desc: bool = False) -> "SupabaseQuery": ...
    def limit(self, count: int) -> "SupabaseQuery": ...
    def execute(self) -> object: ...

@runtime_checkable
class SupabaseClientLike(Protocol):
    def table(self, name: str) -> SupabaseQuery: ...

@runtime_checkable
class RedisClientLike(Protocol):
    def get(self, key: str) -> object: ...
    def setex(self, key: str, time: int, value: str) -> object: ...
    def delete(self, *keys: str) -> object: ...
    def keys(self, pattern: str) -> Sequence[str]: ...
    def ping(self) -> object: ...
    def info(self) -> Mapping[str, object]: ...

class CacheManager:
    """
    Gestor de caché multi-nivel con TTL configurable
    """
    
    def __init__(self, default_ttl: int = 3600):  # 1 hora por defecto
        super().__init__()
        self.default_ttl: int = default_ttl
        self.redis_client: RedisClientLike | None = None
        self.supabase: SupabaseClientLike | None = None
        self._memory_cache: dict[str, object] = {}  # Cache L1 en memoria
        self._memory_timestamps: dict[str, float] = {}
        
        # Inicializar conexiones
        self._init_redis()
        self._init_supabase()
    
    def _init_redis(self):
        """Inicializar conexión Redis"""
        try:
            self.redis_client = cast(
                RedisClientLike,
                cast(
                    object,
                    redis.from_url(
                        settings.CELERY_BROKER_URL,
                        decode_responses=True,
                        socket_connect_timeout=5,
                        socket_timeout=5,
                    ),
                ),
            )
            # Test connection
            _ = self.redis_client.ping()
            logger.info("Redis cache conectado correctamente")
        except Exception as e:
            logger.warning(f"Redis no disponible, usando solo memoria: {e}")
            self.redis_client = None
    
    def _init_supabase(self):
        """Inicializar cliente Supabase"""
        try:
            # Casting intermedio vía object para satisfacer a Pyright con Protocols
            self.supabase = cast(
                SupabaseClientLike,
                cast(
                    object,
                    create_client(
                        settings.SUPABASE_URL,
                        settings.SUPABASE_SERVICE_ROLE_KEY,
                    ),
                ),
            )
            logger.info("Supabase cache conectado correctamente")
        except Exception as e:
            logger.error(f"Error conectando Supabase: {e}")
            self.supabase = None
    
    def _generate_key(self, namespace: str, identifier: str) -> str:
        """Generar clave de caché consistente"""
        return f"cache:{namespace}:{identifier}"
    
    def _is_expired(self, timestamp: float, ttl: int) -> bool:
        """Verificar si un elemento ha expirado"""
        return time.time() - timestamp > ttl
    
    # ==================== CACHE L1 (MEMORIA) ====================
    
    def _get_from_memory(self, key: str, ttl: int) -> object | None:
        """Obtener valor del cache L1 (memoria)"""
        if key not in self._memory_cache:
            return None
        
        timestamp = self._memory_timestamps.get(key, 0)
        if self._is_expired(timestamp, ttl):
            # Limpiar entrada expirada
            _ = self._memory_cache.pop(key, None)
            _ = self._memory_timestamps.pop(key, None)
            return None
        
        logger.debug(f"Cache L1 HIT: {key}")
        return self._memory_cache[key]
    
    def _set_to_memory(self, key: str, value: object):
        """Guardar valor en cache L1 (memoria)"""
        self._memory_cache[key] = value
        self._memory_timestamps[key] = time.time()
        logger.debug(f"Cache L1 SET: {key}")
    
    def _delete_from_memory(self, key: str):
        """Eliminar valor del cache L1"""
        _ = self._memory_cache.pop(key, None)
        _ = self._memory_timestamps.pop(key, None)
    
    # ==================== CACHE L2 (REDIS) ====================
    
    def _get_from_redis(self, key: str) -> object | None:
        """Obtener valor del cache L2 (Redis)"""
        if not self.redis_client:
            return None
        
        try:
            value = self.redis_client.get(key)
            if value and isinstance(value, (str, bytes)):
                logger.debug(f"Cache L2 HIT: {key}")
                return cast(object, json.loads(value))
            return None
        except Exception as e:
            logger.warning(f"Error leyendo Redis: {e}")
            return None
    
    def _set_to_redis(self, key: str, value: object, ttl: int):
        """Guardar valor en cache L2 (Redis)"""
        if not self.redis_client:
            return
        
        try:
            serialized = json.dumps(value, default=str)
            _ = self.redis_client.setex(key, ttl, serialized)
            logger.debug(f"Cache L2 SET: {key} (TTL: {ttl}s)")
        except Exception as e:
            logger.warning(f"Error escribiendo Redis: {e}")
    
    def _delete_from_redis(self, key: str):
        """Eliminar valor del cache L2 (Redis)"""
        if not self.redis_client:
            return
        
        try:
            _ = self.redis_client.delete(key)
            logger.debug(f"Cache L2 DELETE: {key}")
        except Exception as e:
            logger.warning(f"Error eliminando de Redis: {e}")
  
    # ==================== CACHE L3 (DATABASE FALLBACK) ====================

    def _extract_from_identifier(self, namespace: str, identifier: str) -> dict[str, str]:
        """Extrae tenant_id y/o tipos desde el identificador de caché específico por namespace.
        Espera formatos:
          - ml_features: "features_<tenant_id>"
          - ml_predictions: "prediction_<tenant_id>_<prediction_type>"
          - notification_rules: "rules_<tenant_id>"
          - business_config: "config_<tenant_id>"
        Si no coincide, retorna vacío.
        """
        try:
            if namespace == "ml_features" and identifier.startswith("features_"):
                return {"tenant_id": identifier.split("features_", 1)[1]}
            if namespace == "ml_predictions" and identifier.startswith("prediction_"):
                _, rest = identifier.split("prediction_", 1)
                parts = rest.split("_", 1)
                if len(parts) == 2:
                    return {"tenant_id": parts[0], "prediction_type": parts[1]}
                else:
                    return {"tenant_id": parts[0]}
            if namespace == "notification_rules" and identifier.startswith("rules_"):
                return {"tenant_id": identifier.split("rules_", 1)[1]}
            if namespace == "business_config" and identifier.startswith("config_"):
                return {"tenant_id": identifier.split("config_", 1)[1]}
        except Exception:
            pass
        return {}

    def _get_from_database(self, namespace: str, identifier: str) -> object | None:
        """Fallback a base de datos según el namespace"""
        if not self.supabase:
            return None
        
        try:
            params = self._extract_from_identifier(namespace, identifier)
            tenant_id = params.get("tenant_id")
            # Cliente Supabase ya no nulo (narrowing por el guard anterior)
            sb: SupabaseClientLike = self.supabase
            if namespace == "ml_features" and tenant_id:
                # Obtener última fila de features por fecha
                result = (
                    sb
                    .table("ml_features")
                    .select("*")
                    .eq("tenant_id", tenant_id)
                    .order("feature_date", desc=True)
                    .limit(1)
                    .execute()
                )
                data_list = cast(list[object] | None, getattr(result, "data", None))
                if data_list:
                    return data_list[0]
                return None
            
            elif namespace == "ml_predictions" and tenant_id:
                query = (
                    sb
                    .table("ml_predictions")
                    .select("*")
                    .eq("tenant_id", tenant_id)
                )
                if "prediction_type" in params:
                    query = query.eq("prediction_type", params["prediction_type"])
                result = query.order("prediction_date", desc=True).limit(1).execute()
                data_list = cast(list[object] | None, getattr(result, "data", None))
                if data_list:
                    return data_list[0]
                return None
            
            elif namespace == "notification_rules" and tenant_id:
                # Reglas activas por tenant
                result = (
                    sb
                    .table("notification_rules")
                    .select("*")
                    .eq("tenant_id", tenant_id)
                    .eq("active", True)
                    .execute()
                )
                data_list = cast(list[object] | None, getattr(result, "data", None))
                return data_list if isinstance(data_list, list) else None
            
            elif namespace == "business_config" and tenant_id:
                result = (
                    sb
                    .table("tenant_settings")
                    .select("*")
                    .eq("tenant_id", tenant_id)
                    .limit(1)
                    .execute()
                )
                data_list = cast(list[object] | None, getattr(result, "data", None))
                if data_list:
                    return data_list[0]
                return None
            
            # No fallback posible si el identificador no es parseable
            return None
        
        except Exception as e:
            logger.error(f"Error en fallback DB: {e}")
            return None
    
    # ==================== API PÚBLICA ====================
    
    def get(self, namespace: str, identifier: str, ttl: int | None = None) -> object | None:
        """
        Obtener valor del caché multi-nivel
        
        Args:
            namespace: Categoría del dato (ml_features, notification_rules, etc.)
            identifier: ID único (business_id, user_id, etc.)
            ttl: Time to live en segundos (default: 1 hora)
        """
        ttl = ttl or self.default_ttl
        key = self._generate_key(namespace, identifier)
        
        # L1: Intentar memoria
        value = self._get_from_memory(key, ttl)
        if value is not None:
            return value
        
        # L2: Intentar Redis
        value = self._get_from_redis(key)
        if value is not None:
            # Guardar en L1 para próximas consultas
            self._set_to_memory(key, value)
            return value
        
        # L3: Fallback a base de datos
        value = self._get_from_database(namespace, identifier)
        if value is not None:
            # Guardar en ambos niveles
            self._set_to_memory(key, value)
            self._set_to_redis(key, value, ttl)
            logger.info(f"Cache MISS -> DB fallback: {key}")
            return value
        
        logger.debug(f"Cache MISS completo: {key}")
        return None
    
    def set(self, namespace: str, identifier: str, value: object, ttl: int | None = None):
        """
        Guardar valor en todos los niveles de caché
        """
        ttl = ttl or self.default_ttl
        key = self._generate_key(namespace, identifier)
        
        # Guardar en ambos niveles
        self._set_to_memory(key, value)
        self._set_to_redis(key, value, ttl)
        
        logger.info(f"Cache SET: {key}")
    
    def delete(self, namespace: str, identifier: str):
        """
        Invalidar caché en todos los niveles
        """
        key = self._generate_key(namespace, identifier)
        
        self._delete_from_memory(key)
        self._delete_from_redis(key)
        
        logger.info(f"Cache INVALIDATED: {key}")
    
    def invalidate_pattern(self, pattern: str):
        """
        Invalidar múltiples claves por patrón (solo Redis)
        """
        # Limpiar L1 (memoria)
        mem_prefix = f"cache:{pattern}"
        try:
            mem_keys = [k for k in list(self._memory_cache.keys()) if k.startswith(mem_prefix)]
            for k in mem_keys:
                _ = self._memory_cache.pop(k, None)
                _ = self._memory_timestamps.pop(k, None)
        except Exception as e:
            logger.warning(f"Error invalidando patrón en memoria: {e}")

        # Limpiar L2 (Redis)
        if self.redis_client:
            try:
                keys = list(self.redis_client.keys(f"cache:{pattern}*"))
                if keys:
                    _ = self.redis_client.delete(*keys)
                logger.info(f"Cache pattern invalidated: {pattern} ({len(keys)} keys)")
            except Exception as e:
                logger.warning(f"Error invalidando patrón en Redis: {e}")
    
    def clear_all(self):
        """
        Limpiar todo el caché
        """
        # Limpiar memoria
        self._memory_cache.clear()
        self._memory_timestamps.clear()
        
        # Limpiar Redis
        if self.redis_client:
            try:
                keys = list(self.redis_client.keys("cache:*"))
                if keys:
                    _ = self.redis_client.delete(*keys)
                logger.info("Cache completamente limpiado")
            except Exception as e:
                logger.warning(f"Error limpiando Redis: {e}")
    
    def get_stats(self) -> dict[str, object]:
        """
        Obtener estadísticas del caché
        """
        stats: dict[str, object] = {
            "memory_entries": len(self._memory_cache),
            "redis_available": self.redis_client is not None,
            "supabase_available": self.supabase is not None,
            "default_ttl": self.default_ttl
        }
        
        if self.redis_client:
            try:
                info = self.redis_client.info()
                stats["redis_memory_used"] = str(info.get("used_memory_human", "N/A"))
                val = info.get("connected_clients", 0)
                stats["redis_connected_clients"] = int(val) if isinstance(val, (int, str)) else 0
            except Exception:
                pass
        
        return stats

# Instancia global del cache manager
cache_manager = CacheManager()
