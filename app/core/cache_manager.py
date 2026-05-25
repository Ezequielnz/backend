"""
cache_manager.py — Caché en memoria (L1 only)
===============================================
Versión simplificada para la arquitectura desktop.
Redis y Supabase eliminados — solo caché en memoria con TTL.
La API pública es compatible con el código original para evitar
cambios en los consumidores.
"""
import json
import time
import logging
from typing import Any

logger = logging.getLogger(__name__)


class CacheManager:
    """Gestor de caché en memoria con TTL configurable."""

    def __init__(self, default_ttl: int = 3600):
        self.default_ttl: int = default_ttl
        self._cache: dict[str, Any] = {}
        self._timestamps: dict[str, float] = {}

    # ── helpers internos ────────────────────────────────────────────────────────

    def _key(self, namespace: str, identifier: str) -> str:
        return f"cache:{namespace}:{identifier}"

    def _expired(self, key: str, ttl: int) -> bool:
        ts = self._timestamps.get(key)
        if ts is None:
            return True
        return (time.time() - ts) > ttl

    def _evict(self, key: str) -> None:
        self._cache.pop(key, None)
        self._timestamps.pop(key, None)

    # ── API pública (compatible con la versión anterior) ────────────────────────

    def get(self, namespace: str, identifier: str, ttl: int | None = None) -> Any:
        ttl = ttl or self.default_ttl
        key = self._key(namespace, identifier)
        if self._expired(key, ttl):
            self._evict(key)
            return None
        logger.debug("Cache HIT: %s", key)
        return self._cache.get(key)

    def set(self, namespace: str, identifier: str, value: Any, ttl: int | None = None) -> None:
        key = self._key(namespace, identifier)
        self._cache[key] = value
        self._timestamps[key] = time.time()
        logger.debug("Cache SET: %s", key)

    def delete(self, namespace: str, identifier: str) -> None:
        self._evict(self._key(namespace, identifier))

    def invalidate_pattern(self, pattern: str) -> None:
        prefix = f"cache:{pattern}"
        keys = [k for k in list(self._cache) if k.startswith(prefix)]
        for k in keys:
            self._evict(k)
        if keys:
            logger.info("Cache pattern invalidated: %s (%d keys)", pattern, len(keys))

    def clear_all(self) -> None:
        self._cache.clear()
        self._timestamps.clear()
        logger.info("Cache completamente limpiado")

    def get_stats(self) -> dict[str, Any]:
        return {
            "memory_entries": len(self._cache),
            "redis_available": False,
            "supabase_available": False,
            "default_ttl": self.default_ttl,
        }


# Instancia global
cache_manager = CacheManager()
