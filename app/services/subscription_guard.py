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
        # Según el requerimiento: "no debe de salir un error si el cliente no pagó."
        # Como aún se está probando el sistema, permitimos el acceso pero registramos una advertencia
        logger.warning(
            f"Usuario {user_id} requiere pago (estado: {subscription_status}), "
            "pero se permite acceso temporal por fase de pruebas."
        )
        # Devolver el current_user para no bloquear las llamadas a la API
        return current_user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking subscription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error validando el estado de la suscripción"
        )
