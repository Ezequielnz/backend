from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, status
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.db.supabase_client import get_supabase_service_client as get_db
from app.api.deps import get_current_user
from app.types.auth import User
from app.services.mercadopago_service import mp_service
from app.core.config import settings
import logging
import hmac
import hashlib
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter()

class CheckoutRequest(BaseModel):
    referral_code: Optional[str] = None

class WebhookResponse(BaseModel):
    status: str

@router.post("/checkout")
async def create_checkout(
    request: CheckoutRequest,
    current_user: Any = Depends(get_current_user),
    db = Depends(get_db)
):
    """Generates the MP checkout link. Takes into account referrals."""
    try:
        user_id = current_user.get("id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
        user_email = current_user.get("email") if isinstance(current_user, dict) else getattr(current_user, "email", None)
        
        # Check user details in DB
        user_res = db.table("usuarios").select("*").eq("id", user_id).single().execute()
        user_data = user_res.data
        
        if not user_data:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
            
        # Determine free months based on referrer
        free_months = 1
        if user_data.get("referrer_type") == "contador":
            free_months = 2
            
        # Create preapproval in MP
        mp_response = await mp_service.create_preapproval_link(
            # pyrefly: ignore [bad-argument-type]
            user_id=user_id,
            # pyrefly: ignore [bad-argument-type]
            user_email=user_email,
            free_months=free_months
        )
        
        # Save preapproval_id in DB to track it
        db.table("usuarios").update({
            "mp_preapproval_id": mp_response["preapproval_id"]
        }).eq("id", user_id).execute()
        
        return {
            "init_point": mp_response["init_point"],
            "preapproval_id": mp_response["preapproval_id"],
            "free_months": free_months
        }
    except Exception as e:
        logger.error(f"Error creating checkout: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_subscription_status(
    current_user: Any = Depends(get_current_user),
    db = Depends(get_db)
):
    """Returns the current subscription status from our DB."""
    user_id = current_user.get("id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
    user_email = current_user.get("email") if isinstance(current_user, dict) else getattr(current_user, "email", None)
    
    # 1. Fast-path settings exemption check
    if user_email and user_email in getattr(settings, "EXEMPT_EMAILS", []):
        return {
            "subscription_status": "active",
            "trial_end": None,
            "is_exempt": True,
            "free_months_pending": 0
        }
        
    # 2. Query DB safely
    try:
        # Use execute() and check data to avoid exceptions raised by single() when no rows exist
        res = db.table("usuarios").select("subscription_status, trial_end, is_exempt, free_months_pending").eq("id", user_id).limit(1).execute()
        if not res.data:
            logger.warning(f"Usuario {user_id} no encontrado en tabla usuarios al consultar status.")
            return {
                "subscription_status": "trial",
                "trial_end": None,
                "is_exempt": False,
                "free_months_pending": 0
            }
        data = res.data[0]
    except Exception as e:
        logger.error(f"Error fetching subscription status from DB for user {user_id}: {e}")
        return {
            "subscription_status": "trial",
            "trial_end": None,
            "is_exempt": False,
            "free_months_pending": 0,
            "db_error": True
        }
    
    if data and data.get("subscription_status") == 'trial' and data.get("trial_end"):
        try:
            trial_end_str = data["trial_end"]
            if trial_end_str.endswith('Z'):
                trial_end_str = trial_end_str[:-1] + '+00:00'
            trial_end = datetime.fromisoformat(trial_end_str)
            now = datetime.now(timezone.utc)
            
            if trial_end <= now:
                # Update DB to trial_expired
                try:
                    db.table("usuarios").update({"subscription_status": "trial_expired"}).eq("id", user_id).execute()
                    data["subscription_status"] = "trial_expired"
                except Exception as update_err:
                    logger.error(f"Error updating trial expiration in DB: {update_err}")
                    data["subscription_status"] = "trial_expired"
        except Exception as e:
            logger.error(f"Error checking trial expiration in /status: {e}")
            
    return data

def verify_mp_signature(request: Request, payload: bytes) -> bool:
    """Verifies the webhook signature from Mercado Pago."""
    x_signature = request.headers.get("x-signature")
    x_request_id = request.headers.get("x-request-id")
    
    if not x_signature or not x_request_id or not settings.MP_WEBHOOK_SECRET:
        # If no secret configured or headers missing, we might want to fail or just rely on the API check
        logger.warning("Faltan headers de firma de MP o el secret no está configurado.")
        return False
        
    try:
        parts = dict(part.split("=") for part in x_signature.split(","))
        ts = parts.get("ts")
        v1 = parts.get("v1")
        
        if not ts or not v1:
            return False
            
        manifest = f"id:{x_request_id};request-id:{x_request_id};ts:{ts};"
        sha = hmac.new(
            settings.MP_WEBHOOK_SECRET.encode(),
            manifest.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return sha == v1
    except Exception as e:
        logger.error(f"Error validating signature: {e}")
        return False

async def process_payment_async(payment_id: str, db):
    """Background task to process a payment webhook safely"""
    try:
        # 1. Fetch payment from MP API to prevent spoofing
        payment = await mp_service.get_payment_info(payment_id)
        
        if not payment:
            logger.error(f"Payment {payment_id} no encontrado en MP")
            return
            
        status = payment.get("status")
        preapproval_id = payment.get("order", {}).get("id") # Usually preapproval links to order or directly in metadata
        amount = payment.get("transaction_amount", 0)
        external_reference = payment.get("external_reference")
        
        # In Preapproval, the payment might not have external_reference directly if generated automatically.
        # We need to find the user via mp_preapproval_id or external_reference
        user_id = external_reference
        
        if not user_id and preapproval_id:
             user_res = db.table("usuarios").select("id").eq("mp_preapproval_id", preapproval_id).execute()
             if user_res.data:
                 user_id = user_res.data[0]["id"]
                 
        if not user_id:
            logger.error(f"No se pudo determinar el usuario para el pago {payment_id}")
            return
            
        user_res = db.table("usuarios").select("*").eq("id", user_id).single().execute()
        user = user_res.data
        
        # 2. Check if we already processed this payment
        hist_res = db.table("mp_pagos_historial").select("id").eq("mp_payment_id", str(payment_id)).execute()
        if hist_res.data:
            logger.info(f"El pago {payment_id} ya fue procesado.")
            return
            
        # 3. Handle Authorized / Approved payment
        if status in ["approved", "authorized"]:
            # Check if this is the first real payment (if status was previously trial/null)
            is_first_real = user.get("subscription_status") in ["trial", None, "inactive"]
            
            # Update user status
            db.table("usuarios").update({
                "subscription_status": "active"
            }).eq("id", user_id).execute()
            
            # Commission calculation
            comision_monto = 0
            comision_receptor_id = None
            
            if user.get("referrer_type") == "contador" and user.get("referred_by_user_id"):
                comision_monto = float(amount) * 0.20
                comision_receptor_id = user.get("referred_by_user_id")
                
            # Insert into history
            db.table("mp_pagos_historial").insert({
                "usuario_id": user_id,
                "mp_payment_id": str(payment_id),
                "mp_preapproval_id": preapproval_id or user.get("mp_preapproval_id"),
                "monto": amount,
                "estado": status,
                "fecha_pago": payment.get("date_approved"),
                "es_primer_pago_real": is_first_real,
                "comision_monto": comision_monto,
                "comision_receptor_id": comision_receptor_id,
                "raw_payload": payment
            }).execute()
            
            # Post-processing: Process OperiXML referral benefit
            if is_first_real and user.get("referrer_type") == "operixml" and user.get("referred_by_user_id"):
                referente_id = user.get("referred_by_user_id")
                
                # Check if it doesn't exist yet
                ben_res = db.table("referidos_operixml_beneficios").select("id").eq("referido_id", user_id).execute()
                if not ben_res.data:
                    # Create benefit record
                    db.table("referidos_operixml_beneficios").insert({
                        "referente_id": referente_id,
                        "referido_id": user_id,
                        "estado": "pendiente_aplicar",
                        "primer_pago_referido_id": str(payment_id),
                        "fecha_primer_pago": payment.get("date_approved")
                    }).execute()
                    
                    # Add 1 month pending to both
                    # Need RPC to increment safely, or do it sequentially
                    ref_user = db.table("usuarios").select("free_months_pending").eq("id", referente_id).single().execute()
                    if ref_user.data:
                        db.table("usuarios").update({
                            "free_months_pending": ref_user.data.get("free_months_pending", 0) + 1
                        }).eq("id", referente_id).execute()
                        
                    db.table("usuarios").update({
                        "free_months_pending": user.get("free_months_pending", 0) + 1
                    }).eq("id", user_id).execute()

            # The transfer for contadores will be processed via a Celery beat job reading the history table,
            # to ensure robust retries and verification by admin.
            
    except Exception as e:
        logger.error(f"Error procesando pago asincrono {payment_id}: {e}")


@router.post("/webhook")
async def mercadopago_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db = Depends(get_db)
):
    """
    Public webhook endpoint to receive notifications from Mercado Pago.
    Does not require JWT authentication.
    """
    # 1. Parse payload
    payload_bytes = await request.body()
    try:
        payload = await request.json()
    except Exception:
        return {"status": "ok"} # MP will retry if we fail, so we return OK if parsing fails
        
    # MP sends `action`, `type` and `data.id`
    # E.g. {"action": "payment.created", "data": {"id": "12345"}}
    
    topic = payload.get("type") or payload.get("topic")
    action = payload.get("action")
    data_id = payload.get("data", {}).get("id")
    
    # Optional: Verify signature (uncomment when secret is configured in production)
    # is_valid = verify_mp_signature(request, payload_bytes)
    # if not is_valid:
    #     logger.warning("Firma de MP no válida.")
    
    if topic == "payment" and data_id:
        # Schedule the processing in background so we respond to MP quickly
        background_tasks.add_task(process_payment_async, str(data_id), db)
        
    elif topic == "preapproval" and data_id:
        # Check preapproval status changes (cancelled, paused)
        try:
            preapp = await mp_service.get_preapproval_status(str(data_id))
            status = preapp.get("status")
            
            user_res = db.table("usuarios").select("id").eq("mp_preapproval_id", str(data_id)).execute()
            if user_res.data:
                user_id = user_res.data[0]["id"]
                if status == "cancelled":
                    db.table("usuarios").update({"subscription_status": "cancelled"}).eq("id", user_id).execute()
                elif status == "paused":
                    db.table("usuarios").update({"subscription_status": "past_due"}).eq("id", user_id).execute()
        except Exception as e:
            logger.error(f"Error checking preapproval webhook for {data_id}: {e}")

    return {"status": "success"}

@router.get("/referral-code")
async def get_referral_code(current_user: Any = Depends(get_current_user), db = Depends(get_db)):
    """Returns the user's referral code and their status."""
    user_id = current_user.get("id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
    res = db.table("usuarios").select("referral_code, free_months_pending, total_comision_ganada").eq("id", user_id).single().execute()
    return res.data

@router.get("/validate-referral/{code}")
async def validate_referral_code(code: str, db = Depends(get_db)):
    """Validates if a referral code exists before registration."""
    res = db.table("usuarios").select("id, nombre").eq("referral_code", code).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Código inválido")
    
    user = res.data[0]
    return {
        "valid": True,
        "referrer_name": user.get("nombre"),
        "type": "operixml"
    }

@router.get("/referrals")
async def get_my_referrals(current_user: Any = Depends(get_current_user), db = Depends(get_db)):
    """Returns the list of users referred by the current user."""
    user_id = current_user.get("id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
    res = db.table("usuarios").select("nombre, apellido, email, subscription_status, created_at").eq("referred_by_user_id", user_id).execute()
    return res.data


@router.post("/cancel")
async def cancel_subscription(
    current_user: Any = Depends(get_current_user),
    db = Depends(get_db)
):
    """
    Cancels the user's Mercado Pago preapproval subscription and marks their
    account as 'cancelled' in the database.
    """
    user_id = current_user.get("id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    try:
        # Get the user's preapproval ID from DB
        user_res = db.table("usuarios").select("mp_preapproval_id, subscription_status").eq("id", user_id).single().execute()
        user_data = user_res.data

        if not user_data:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        preapproval_id = user_data.get("mp_preapproval_id")

        # Attempt to cancel in Mercado Pago if there is an active preapproval
        if preapproval_id:
            try:
                await mp_service.cancel_preapproval(preapproval_id)
                logger.info(f"Preapproval {preapproval_id} cancelled in Mercado Pago for user {user_id}")
            except Exception as mp_err:
                # Log the error but continue — still mark as cancelled in our DB
                logger.error(f"Error cancelling preapproval {preapproval_id} in MP: {mp_err}")

        # Update user status in DB
        db.table("usuarios").update({
            "subscription_status": "cancelled",
            "mp_preapproval_id": None
        }).eq("id", user_id).execute()

        logger.info(f"User {user_id} subscription marked as cancelled.")
        return {"message": "Suscripción cancelada exitosamente."}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling subscription for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Error al cancelar la suscripción.")

