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
        # 1. Check if the user is exempt via email before querying the DB (fast path/fallback)
        user_email = current_user.get("email") if isinstance(current_user, dict) else getattr(current_user, "email", None)
        from app.core.config import settings
        if user_email and user_email in getattr(settings, "EXEMPT_EMAILS", []):
            logger.info(f"User {user_email} is exempt via settings config.")
            return current_user

        user_id = current_user.get("id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
        if not user_id:
            raise HTTPException(status_code=401, detail="Usuario no identificado")

        # 2. Query the DB to check latest subscription status
        try:
            response = db.table("usuarios").select("subscription_status, trial_end, is_exempt").eq("id", user_id).limit(1).execute()
        except Exception as db_exc:
            logger.exception(f"Database query failed while checking subscription for user {user_id}: {db_exc}")
            # If the database is inaccessible, we should allow GET/OPTIONS requests to proceed.
            if request.method in ("GET", "OPTIONS"):
                logger.warning("Allowing GET/OPTIONS request to proceed despite DB query error.")
                return current_user
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error validando el estado de la suscripción (DB inaccesible): {str(db_exc)}"
            )

        if not response.data:
            # Si el usuario no existe en la tabla, lo dejamos pasar temporalmente (o podrías decidir qué hacer)
            logger.warning(f"Usuario {user_id} no encontrado en tabla usuarios.")
            return current_user

        user_data = response.data[0]
        is_exempt = user_data.get("is_exempt") is True

        # 3. Exempt users can bypass the paywall
        if is_exempt:
            return current_user

        subscription_status = user_data.get("subscription_status")
        trial_end_str = user_data.get("trial_end")

        # 4. Check and handle trial expiration
        if subscription_status == 'trial' and trial_end_str:
            try:
                # Handle Z timezone indicator
                clean_trial_end = trial_end_str
                if clean_trial_end.endswith('Z'):
                    clean_trial_end = clean_trial_end[:-1] + '+00:00'
                trial_end = datetime.fromisoformat(clean_trial_end)
                if trial_end.tzinfo is None:
                    trial_end = trial_end.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)

                if trial_end <= now:
                    # Update DB to trial_expired
                    try:
                        db.table("usuarios").update({"subscription_status": "trial_expired"}).eq("id", user_id).execute()
                        logger.info(f"Usuario {user_id} trial expiró. Estado actualizado en DB a trial_expired.")
                        subscription_status = "trial_expired"
                    except Exception as db_err:
                        logger.error(f"Error actualizando estado de trial expirado en DB para usuario {user_id}: {db_err}")
            except Exception as e:
                logger.error(f"Error parsing trial_end date: {e} for user {user_id}")

        # 5. Check active subscription
        if subscription_status == 'active':
            return current_user

        # 6. Check active trial
        if subscription_status == 'trial' and trial_end_str:
            try:
                clean_trial_end = trial_end_str
                if clean_trial_end.endswith('Z'):
                    clean_trial_end = clean_trial_end[:-1] + '+00:00'
                trial_end = datetime.fromisoformat(clean_trial_end)
                if trial_end.tzinfo is None:
                    trial_end = trial_end.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                if trial_end > now:
                    return current_user
            except Exception:
                pass

        # 7. If we reach here, the user is neither exempt, active, nor in an active trial
        # Allow read-only access so they can view the dashboard and see the notification banner
        if request.method in ("GET", "OPTIONS"):
            return current_user

        logger.warning(f"Acceso denegado: Usuario {user_id} requiere pago (estado: {subscription_status}). Method: {request.method}")
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Suscripción requerida para realizar acciones. Por favor regularice su pago."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error checking subscription")
        if request.method in ("GET", "OPTIONS"):
            logger.warning("Allowing GET/OPTIONS request to proceed despite unexpected error in guard.")
            return current_user
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error validando el estado de la suscripción: {str(e)}"
        )
