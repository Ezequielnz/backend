from fastapi import HTTPException, status, Depends, Request
from datetime import datetime, timezone
from app.core.config import settings
from app.db.supabase_client import get_supabase_client, get_supabase_service_client

async def check_subscription_access(request: Request):
    """
    Dependency to check if the user has an active subscription or valid trial.
    Raises 403 if the user is in read-only mode.
    """
    # Temporarily disabled per user request
    return True
