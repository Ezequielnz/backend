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
        # current_user puede ser un dict (UserData) o un objeto Pydantic (User)
        user_id = current_user.get("id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Usuario no identificado")
            
        # Usamos limit(1) en lugar de single() para evitar que lance una excepción si no hay filas
        response = db.table("usuarios").select("subscription_status, trial_end, is_exempt").eq("id", user_id).limit(1).execute()
        
        if not response.data:
            # Si el usuario no existe en la tabla, lo dejamos pasar temporalmente (o podrías decidir qué hacer)
            logger.warning(f"Usuario {user_id} no encontrado en tabla usuarios.")
            return current_user
            
        user_data = response.data[0]
        is_exempt = user_data.get("is_exempt") is True
        
        # 1. Exempt users can bypass the paywall
        if is_exempt:
            return current_user
            
        subscription_status = user_data.get("subscription_status")
        trial_end_str = user_data.get("trial_end")
        
        # 2. Check and handle trial expiration
        if subscription_status == 'trial' and trial_end_str:
            try:
                # Handle Z timezone indicator
                clean_trial_end = trial_end_str
                if clean_trial_end.endswith('Z'):
                    clean_trial_end = clean_trial_end[:-1] + '+00:00'
                trial_end = datetime.fromisoformat(clean_trial_end)
                now = datetime.now(timezone.utc)
                
                if trial_end <= now:
                    # Update DB to trial_expired
                    try:
                        db.table("usuarios").update({"subscription_status": "trial_expired"}).eq("id", user_id).execute()
                        logger.info(f"Usuario {user_id} trial expiró. Estado actualizado en DB a trial_expired.")
                        subscription_status = "trial_expired"
                    except Exception as db_err:
                        logger.error(f"Error actualizando estado de trial expirado en DB para usuario {user_id}: {db_err}")
            except ValueError as e:
                logger.error(f"Error parsing trial_end date: {e} for user {user_id}")
        
        # 3. Check active subscription
        if subscription_status == 'active':
            return current_user
            
        # 4. Check active trial
        if subscription_status == 'trial' and trial_end_str:
            try:
                clean_trial_end = trial_end_str
                if clean_trial_end.endswith('Z'):
                    clean_trial_end = clean_trial_end[:-1] + '+00:00'
                trial_end = datetime.fromisoformat(clean_trial_end)
                now = datetime.now(timezone.utc)
                if trial_end > now:
                    return current_user
            except Exception:
                pass
                
        # If we reach here, the user is neither exempt, active, nor in an active trial
        logger.warning(f"Acceso denegado: Usuario {user_id} requiere pago (estado: {subscription_status}).")
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Suscripción requerida"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking subscription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error validando el estado de la suscripción"
        )
