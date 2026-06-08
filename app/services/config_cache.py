"""
app/services/config_cache.py

TTL-based in-memory cache for negocio_configuracion.
Reduces repeated DB round-trips for config reads on every product operation.

Thread-safety note: The GIL protects simple dict reads/writes in CPython.
For multi-process deployments (e.g. Gunicorn workers) each process has its own
cache — this is acceptable because the TTL is short (60 s).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal cache store
# ---------------------------------------------------------------------------
# Maps business_id → (config_dict, timestamp_when_cached)
_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}

# Cache time-to-live in seconds.  60 s is a good balance:
# config changes are rare, so staleness is acceptable for 1 minute.
TTL: float = 60.0

# Columns we always fetch — keep in sync with BranchSettings schema
_SELECT_COLS = "catalogo_producto_modo, inventario_modo"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_negocio_config(business_id: str, supabase) -> Dict[str, Any]:
    """
    Return the negocio_configuracion row for *business_id*, using the in-memory
    cache when the entry is still fresh.

    Falls back gracefully to safe defaults if the row doesn't exist yet.

    Args:
        business_id: UUID of the negocio.
        supabase:    Any Supabase client with .table() access
                     (anon, user-scoped, or service-role all work).

    Returns:
        dict with at least:
            catalogo_producto_modo: "compartido" | "por_sucursal"
            inventario_modo:        "centralizado" | "por_sucursal"
    """
    now = time.monotonic()

    # Cache hit?
    cached = _cache.get(business_id)
    if cached is not None:
        data, ts = cached
        if now - ts < TTL:
            logger.debug("config_cache HIT for business_id=%s", business_id)
            return data

    # Cache miss or expired — fetch from DB
    logger.debug("config_cache MISS for business_id=%s — fetching from DB", business_id)
    try:
        resp = (
            supabase
            .table("negocio_configuracion")
            .select(_SELECT_COLS)
            .eq("negocio_id", business_id)
            .limit(1)
            .execute()
        )
        config: Dict[str, Any] = resp.data[0] if resp.data else {}
    except Exception as exc:
        logger.warning(
            "config_cache: failed to fetch config for %s — using defaults. Error: %s",
            business_id,
            exc,
        )
        config = {}

    # Apply defaults for any missing keys
    config.setdefault("catalogo_producto_modo", "compartido")
    config.setdefault("inventario_modo", "centralizado")

    _cache[business_id] = (config, now)
    return config


def invalidate_negocio_config(business_id: str) -> None:
    """
    Evict the cached configuration for *business_id*.

    Should be called after updating negocio_configuracion so that the next
    request picks up the fresh values from the DB.
    """
    removed = _cache.pop(business_id, None)
    if removed is not None:
        logger.info("config_cache: invalidated cache for business_id=%s", business_id)


def get_cached_business_ids() -> list:
    """Return all business_ids currently held in the cache (useful for debugging)."""
    return list(_cache.keys())
