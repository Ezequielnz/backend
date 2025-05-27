from typing import List, Any, Optional, Dict
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Response
from supabase.client import Client

from app.db.supabase_client import get_supabase_client
from app.api import deps
from app.schemas.usuario import Usuario as CurrentUserSchema
from app.schemas.plan import PlanResponse
from app.schemas.suscripcion import SuscripcionCreate, SuscripcionResponse, SuscripcionUpdate

router = APIRouter()

# --- Mock Payment Gateway Functions ---
async def process_payment_and_create_subscription_mock(
    user_id: str, 
    plan_id: int, 
    payment_token: Optional[str]
) -> Dict[str, Any]:
    """
    Mocks interaction with a payment gateway to process payment and create a subscription.
    In a real scenario, this would involve calls to Stripe, MercadoPago, etc.
    """
    print(f"Mock Payment Gateway: Processing payment for user {user_id}, plan {plan_id} with token '{payment_token}'.")
    # Simulate success and return a mock gateway subscription ID and customer ID
    if payment_token == "fail_token": # Simulate a payment failure
        return {
            "success": False,
            "gateway_subscription_id": None,
            "gateway_customer_id": None,
            "error_message": "Payment failed at gateway."
        }
    
    return {
        "success": True,
        "gateway_subscription_id": f"mock_sub_{datetime.now().timestamp()}",
        "gateway_customer_id": f"mock_cus_{user_id}",
        "message": "Subscription created successfully at gateway."
    }

async def cancel_gateway_subscription_mock(gateway_subscription_id: str) -> Dict[str, Any]:
    """
    Mocks cancelling a subscription at the payment gateway.
    """
    print(f"Mock Payment Gateway: Cancelling subscription {gateway_subscription_id}.")
    if not gateway_subscription_id:
         return {"success": False, "message": "No gateway subscription ID provided."}
    return {"success": True, "message": "Subscription cancelled successfully at gateway."}
# --- End Mock Payment Gateway Functions ---


@router.post("/", response_model=SuscripcionResponse, status_code=status.HTTP_201_CREATED)
async def create_subscription(
    *,
    suscripcion_in: SuscripcionCreate,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user)
) -> Any:
    """
    Subscribe the current user to a plan.
    """
    # 1. Validate plan_id
    plan_response = await supabase.table("planes").select("*").eq("id", suscripcion_in.plan_id).eq("activo", True).maybe_single().execute()
    if not plan_response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Active plan with ID {suscripcion_in.plan_id} not found.")
    plan_db = plan_response.data

    # 2. Check for existing active subscription (simple check: prevent multiple active subscriptions)
    active_subs_response = await supabase.table("suscripciones") \
        .select("id, estado, plan_id") \
        .eq("usuario_id", str(current_user.id)) \
        .eq("estado", "activa") \
        .execute()
    if active_subs_response.data:
        # More complex logic could handle upgrades/downgrades or plan changes.
        # For now, if an active subscription exists, prevent creating a new one.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already has an active subscription. Please manage it instead.")

    # 3. Interact with (mock) payment gateway
    gateway_result = await process_payment_and_create_subscription_mock(
        user_id=str(current_user.id),
        plan_id=suscripcion_in.plan_id,
        payment_token=suscripcion_in.payment_token
    )

    if not gateway_result["success"]:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=gateway_result.get("error_message", "Payment processing failed."))

    # 4. Create Suscripcion record in DB
    now = datetime.now(timezone.utc)
    # Assuming a monthly plan for simplicity for fecha_fin
    # In a real system, plan duration (monthly, yearly) would come from the plan_db object
    fecha_fin = now + timedelta(days=30) 

    suscripcion_data = {
        "usuario_id": str(current_user.id),
        "plan_id": suscripcion_in.plan_id,
        "fecha_inicio": now.isoformat(),
        "fecha_fin": fecha_fin.isoformat(),
        "estado": "activa",
        "gateway_id": gateway_result["gateway_subscription_id"],
        "gateway_customer_id": gateway_result["gateway_customer_id"],
        "ultimo_pago_id": f"mock_payment_{datetime.now().timestamp()}", # Simulate a payment ID
        "creado_en": now.isoformat(),
        "actualizado_en": now.isoformat(),
    }
    
    created_suscripcion_response = await supabase.table("suscripciones").insert(suscripcion_data).select("*, plan:planes(*)").single().execute()
    
    if not created_suscripcion_response.data:
        # This is a critical error, payment was processed but subscription not saved.
        # Needs robust handling (e.g., logging, alerting admin, attempting retry or refund).
        print(f"CRITICAL ERROR: Payment processed (mock) but failed to save subscription for user {current_user.id}, plan {suscripcion_in.plan_id}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create subscription after payment.")
    
    return created_suscripcion_response.data


@router.get("/me/", response_model=Optional[SuscripcionResponse])
async def get_my_active_subscription(
    *,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user)
) -> Any:
    """
    Get the current authenticated user's active subscription, if any.
    """
    response = await supabase.table("suscripciones") \
        .select("*, plan:planes(*)") \
        .eq("usuario_id", str(current_user.id)) \
        .eq("estado", "activa") \
        .order("fecha_inicio", desc=True) \
        .limit(1) \
        .maybe_single() \
        .execute()
        
    if not response.data:
        return None # Or raise HTTPException 404 if preferred that no active sub means "not found"
    return response.data


@router.post("/cancel/", response_model=SuscripcionResponse)
async def cancel_my_subscription(
    *,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user)
) -> Any:
    """
    Cancel the current authenticated user's active subscription.
    The subscription remains active until the end of the current billing period (fecha_fin).
    """
    # 1. Find user's active subscription
    active_subs_response = await supabase.table("suscripciones") \
        .select("*") \
        .eq("usuario_id", str(current_user.id)) \
        .eq("estado", "activa") \
        .order("fecha_inicio", desc=True) \
        .limit(1) \
        .maybe_single() \
        .execute()

    if not active_subs_response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription found to cancel.")
    
    active_subscription = active_subs_response.data
    gateway_subscription_id = active_subscription.get("gateway_id")

    # 2. Interact with (mock) payment gateway to cancel
    if gateway_subscription_id: # Only attempt gateway cancellation if ID exists
        gateway_cancel_result = await cancel_gateway_subscription_mock(gateway_subscription_id)
        if not gateway_cancel_result["success"]:
            # If gateway cancellation fails, should we proceed with DB update?
            # For now, we'll proceed but log the gateway error.
            # In a real system, this might require admin intervention or specific error handling.
            print(f"Warning: Failed to cancel subscription at gateway for sub ID {gateway_subscription_id}: {gateway_cancel_result.get('message')}")
            # Depending on policy, you might raise an error here:
            # raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Could not cancel subscription with payment provider. Please try again later.")

    # 3. Update Suscripcion record in DB
    now = datetime.now(timezone.utc)
    update_data = {
        "estado": "cancelada",
        "fecha_cancelacion": now.isoformat(),
        "actualizado_en": now.isoformat()
        # fecha_fin (end of current paid period) typically remains unchanged.
    }
    
    updated_subs_response = await supabase.table("suscripciones") \
        .update(update_data) \
        .eq("id", active_subscription["id"]) \
        .select("*, plan:planes(*)") \
        .single() \
        .execute()
        
    if not updated_subs_response.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update subscription status in database.")
        
    return updated_subs_response.data
