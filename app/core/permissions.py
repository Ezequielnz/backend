from fastapi import HTTPException, status, Depends, Request
from datetime import datetime, timezone
from app.core.config import settings
from app.db.supabase_client import get_supabase_client, get_supabase_service_client

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
        # Use service client to bypass RLS and ensure we can read the user's status
        try:
            supabase = get_supabase_service_client()
            response = supabase.table("usuarios").select("subscription_status, trial_end, is_exempt").eq("id", user_id).execute()
        except Exception as service_error:
            # Fallback: Validation with service role failed (likely 401 or configuration error). 
            # Try using the user's own token if available.
            print(f"Warning: Service client check failed ({service_error}). Attempting fallback with user token.")
            
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                try:
                    from app.db.supabase_client import get_supabase_user_client
                    token = auth_header.replace("Bearer ", "").strip()
                    user_client = get_supabase_user_client(token)
                    response = user_client.table("usuarios").select("subscription_status, trial_end, is_exempt").eq("id", user_id).execute()
                except Exception as user_error:
                    print(f"Error checking subscription with user token: {user_error}")
                    raise service_error
            else:
                 raise service_error
        
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
                print(f"access_denied: User {user_id} ({email}) has trial status but no trial_end date.")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Modo de prueba inválido o expirado. Por favor suscríbase."
                )
            
            trial_end = datetime.fromisoformat(trial_end_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            
            if now > trial_end:
                print(f"access_denied: User {user_id} ({email}) trial expired on {trial_end_str} (now: {now}).")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Su periodo de prueba ha finalizado. El sistema está en modo lectura."
                )
            
            # Trial is valid
            return True

        # If we are here, status is not active or trial (e.g. 'expired', 'cancelled')
        print(f"access_denied: User {user_id} ({email}) subscription status is '{subscription_status}'.")
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
            detail=f"Error verificando estado de suscripción: {str(e)}"
        )
