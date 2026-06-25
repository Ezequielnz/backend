from fastapi import Request, Depends, HTTPException, status
from app.db.supabase_client import get_supabase_service_client as get_db
from app.api.deps import get_current_user
from app.types.auth import User
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

async def check_subscription(
    request: Request,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Dependency to check if the user has an active subscription or an active trial,
    or if they are exempt from paying.
    """
    try:
        # Get user details directly from DB to get the latest subscription status
        response = db.table("usuarios").select("subscription_status, trial_end, is_exempt").eq("id", current_user.id).single().execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="User not found")
            
        user_data = response.data
        
        # 1. Exempt users can bypass the paywall
        if user_data.get("is_exempt") is True:
            return current_user
            
        subscription_status = user_data.get("subscription_status")
        trial_end_str = user_data.get("trial_end")
        
        # 2. Check active subscription
        if subscription_status == 'active':
            return current_user
            
        # 3. Check active trial
        if subscription_status == 'trial' and trial_end_str:
            # Parse trial_end string to datetime aware
            # Supabase returns ISO format string like '2023-10-27T10:00:00+00:00'
            try:
                # Handle Z timezone indicator
                if trial_end_str.endswith('Z'):
                    trial_end_str = trial_end_str[:-1] + '+00:00'
                trial_end = datetime.fromisoformat(trial_end_str)
                now = datetime.now(timezone.utc)
                
                if trial_end > now:
                    return current_user
            except ValueError as e:
                logger.error(f"Error parsing trial_end date: {e} for user {current_user.id}")
                pass # If parsing fails, fall through to block access
                
        # If we reach here, the user is neither exempt, active, nor in an active trial
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "PAYWALL_REQUIRED",
                "message": "Tu período de prueba ha finalizado o tu suscripción está inactiva.",
                "subscription_status": subscription_status
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking subscription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error validando el estado de la suscripción"
        )
