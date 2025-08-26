"""
Sistema de caché multi-nivel para features ML y reglas de notificación
L1: Memoria local (LRU)
L2: Redis 
L3: Fallback a base de datos
"""
import json
import time
from typing import Any, cast
from collections.abc import Mapping, Sequence
# datetime y timedelta no se usan actualmente, comentadas para evitar warnings
# from datetime import datetime, timedelta
import redis
import logging
from app.core.config import settings
from supabase.client import create_client

logger = logging.getLogger(__name__)

class CacheManager:
    """
    Gestor de caché multi-nivel con TTL configurable
    """
    
    def __init__(self, default_ttl: int = 3600):  # 1 hora por defecto
        self.default_ttl = default_ttl
        self.redis_client = None
        self.supabase = None
        self._memory_cache: dict[str, Any] = {}  # Cache L1 en memoria
        self._memory_timestamps: dict[str, float] = {}
        
        # Inicializar conexiones
        self._init_redis()
        self._init_supabase()
    
    def _init_redis(self):
        """Inicializar conexión Redis"""
        try:
            self.redis_client = redis.from_url(
                settings.CELERY_BROKER_URL,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # Test connection
            self.redis_client.ping()
            logger.info("Redis cache conectado correctamente")
        except Exception as e:
            logger.warning(f"Redis no disponible, usando solo memoria: {e}")
            self.redis_client = None
    
    def _init_supabase(self):
        """Inicializar cliente Supabase"""
        try:
            self.supabase = create_client(
                settings.SUPABASE_URL, 
                settings.SUPABASE_SERVICE_ROLE_KEY
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
    
    def _get_from_memory(self, key: str, ttl: int) -> Any | None:
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
    
    def _set_to_memory(self, key: str, value: Any):
        """Guardar valor en cache L1 (memoria)"""
        self._memory_cache[key] = value
        self._memory_timestamps[key] = time.time()
        logger.debug(f"Cache L1 SET: {key}")
    
    def _delete_from_memory(self, key: str):
        """Eliminar valor del cache L1"""
        self._memory_cache.pop(key, None)
        self._memory_timestamps.pop(key, None)
    
    # ==================== CACHE L2 (REDIS) ====================
    
    def _get_from_redis(self, key: str) -> Any | None:
        """Obtener valor del cache L2 (Redis)"""
        if not self.redis_client:
            return None
        
        try:
            value = self.redis_client.get(key)
            if value and isinstance(value, (str, bytes)):
                logger.debug(f"Cache L2 HIT: {key}")
                return json.loads(value)
            return None
        except Exception as e:
            logger.warning(f"Error leyendo Redis: {e}")
            return None
    
    def _set_to_redis(self, key: str, value: Any, ttl: int):
        """Guardar valor en cache L2 (Redis)"""
        if not self.redis_client:
            return
        
        try:
            serialized = json.dumps(value, default=str)
            self.redis_client.setex(key, ttl, serialized)
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
    
    def _get_from_database(self, namespace: str, identifier: str) -> Any | None:
        """Fallback a base de datos según el namespace"""
        if not self.supabase:
            return None
        
        try:
            if namespace == "ml_features":
                result = self.supabase.table("ml_features").select("*").eq("business_id", identifier).execute()
                return result.data[0] if result.data else None
            
            elif namespace == "ml_predictions":
                result = self.supabase.table("ml_predictions").select("*").eq("business_id", identifier).order("created_at", desc=True).limit(1).execute()
                return result.data[0] if result.data else None
            
            elif namespace == "notification_rules":
                result = self.supabase.table("notification_rules").select("*").eq("business_id", identifier).eq("active", True).execute()
                return result.data
            
            elif namespace == "business_config":
                result = self.supabase.table("tenant_settings").select("*").eq("business_id", identifier).execute()
                return result.data[0] if result.data else None
            
            logger.debug(f"Cache L3 HIT: {namespace}:{identifier}")
            return None
            
        except Exception as e:
            logger.error(f"Error en fallback DB: {e}")
            return None
    
    # ==================== API PÚBLICA ====================
    
    def get(self, namespace: str, identifier: str, ttl: int | None = None) -> Any | None:
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
    
    def set(self, namespace: str, identifier: str, value: Any, ttl: int | None = None):
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
        if not self.redis_client:
            return
        
        try:
            keys_resp = self.redis_client.keys(f"cache:{pattern}*")
            keys = cast(Sequence[str], keys_resp)
            if keys:
                _ = self.redis_client.delete(*keys)
            logger.info(f"Cache pattern invalidated: {pattern} ({len(keys)} keys)")
        except Exception as e:
            logger.warning(f"Error invalidando patrón: {e}")
    
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
                keys_resp = self.redis_client.keys("cache:*")
                keys = cast(Sequence[str], keys_resp)
                if keys:
                    _ = self.redis_client.delete(*keys)
                logger.info("Cache completamente limpiado")
            except Exception as e:
                logger.warning(f"Error limpiando Redis: {e}")
    
    def get_stats(self) -> dict[str, Any]:
        """
        Obtener estadísticas del caché
        """
        stats: dict[str, Any] = {
            "memory_entries": len(self._memory_cache),
            "redis_available": self.redis_client is not None,
            "supabase_available": self.supabase is not None,
            "default_ttl": self.default_ttl
        }
        
        if self.redis_client:
            try:
                info_resp = self.redis_client.info()
                info = cast(Mapping[str, Any], info_resp)
                stats["redis_memory_used"] = str(info.get("used_memory_human", "N/A"))
                stats["redis_connected_clients"] = int(cast(int, info.get("connected_clients", 0) or 0))
            except:
                pass
        
        return stats

# Instancia global del cache manager
cache_manager = CacheManager()
