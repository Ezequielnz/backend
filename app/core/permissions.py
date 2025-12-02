from fastapi import HTTPException, status, Depends, Request
from datetime import datetime, timezone
from app.core.config import settings
from app.db.supabase_client import get_supabase_client

async def check_subscription_access(request: Request):
    """
    Dependency to check if the user has an active subscription or valid trial.
    Raises 403 if the user is in read-only mode.
    """
    try:
        # Get user from request state (set by auth middleware/dependency)
        user = getattr(request.state, "user", None)
        if not user:
            # If not authenticated, let the endpoint handle it or it might be a public endpoint
            # But usually this dependency is used after auth.
            # If we are here, we assume auth has passed or we check headers.
            # For now, if no user, we can't check subscription.
            return True

        user_id = user.id
        email = user.email

        # 1. Check if exempt via config (fast check)
        if email in settings.EXEMPT_EMAILS:
            return True

        # 2. Check DB status
        supabase = get_supabase_client()
        response = supabase.table("usuarios").select("subscription_status, trial_end, is_exempt").eq("id", user_id).execute()
        
        if not response.data:
            # User not found in DB? Should not happen if auth passed.
            # Fail safe: allow or deny? Deny to be safe.
            raise HTTPException(status_code=403, detail="Perfil de usuario no encontrado.")

        user_data = response.data[0]
        
        # Check DB exempt flag
        if user_data.get("is_exempt"):
            return True

        subscription_status = user_data.get("subscription_status")
        trial_end_str = user_data.get("trial_end")

        # Active subscription
        if subscription_status == "active":
            return True

        # Trial logic
        if subscription_status == "trial":
            if not trial_end_str:
                # No trial end date? Assume expired or invalid.
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Modo de prueba inválido o expirado. Por favor suscríbase."
                )
            
            trial_end = datetime.fromisoformat(trial_end_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            
            if now > trial_end:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Su periodo de prueba ha finalizado. El sistema está en modo lectura."
                )
            
            # Trial is valid
            return True

        # If we are here, status is not active or trial (e.g. 'expired', 'cancelled')
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Suscripción inactiva. El sistema está en modo lectura."
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error checking subscription: {e}")
        # Fail closed
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Error verificando estado de suscripción."
        )
