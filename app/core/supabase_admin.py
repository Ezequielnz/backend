"""
supabase_admin.py — STUB (DEPRECADO)
=====================================
En la arquitectura desktop no hay Supabase Admin API.
Este módulo expone un stub nulo para que los imports existentes
en auth.py no rompan el servidor mientras se migra el endpoint.
"""
import logging

logger = logging.getLogger(__name__)


class _NullSupabaseAdmin:
    """Objeto nulo — todas las operaciones son no-op con warning."""

    async def get_auth_user(self, user_id: str) -> dict | None:
        logger.warning("[supabase_admin stub] get_auth_user('%s') llamado — no operativo en modo desktop.", user_id)
        return None

    async def update_user(self, user_id: str, attributes: dict) -> dict | None:
        logger.warning("[supabase_admin stub] update_user('%s') llamado — no operativo en modo desktop.", user_id)
        return None

    async def delete_user(self, user_id: str) -> bool:
        logger.warning("[supabase_admin stub] delete_user('%s') llamado — no operativo en modo desktop.", user_id)
        return False

    async def list_users(self) -> list:
        logger.warning("[supabase_admin stub] list_users() llamado — no operativo en modo desktop.")
        return []


supabase_admin = _NullSupabaseAdmin()