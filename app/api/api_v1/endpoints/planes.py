from typing import List, Any, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Response
from supabase.client import Client

from app.db.supabase_client import get_supabase_client
from app.api import deps
from app.schemas.usuario import Usuario as CurrentUserSchema
from app.schemas.plan import PlanCreate, PlanUpdate, PlanResponse

router = APIRouter()

# NOTE: These endpoints should ideally be restricted to admin users.
# This would typically be handled by a more sophisticated RBAC dependency.
# For now, they are protected by standard user authentication.

@router.post("/", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    *,
    plan_in: PlanCreate,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user) # Placeholder for admin check
) -> Any:
    """
    Create a new subscription plan.
    (Ideally, admin access required)
    """
    # TODO: Add admin role check: if current_user.rol != "admin": raise HTTPException(status_code=403, detail="Not authorized")
    
    plan_data = plan_in.model_dump()
    plan_data["creado_en"] = datetime.now(timezone.utc).isoformat()
    plan_data["actualizado_en"] = datetime.now(timezone.utc).isoformat()
    
    response = await supabase.table("planes").insert(plan_data).select("*").single().execute()
    if not response.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create plan.")
    return response.data

@router.get("/", response_model=List[PlanResponse])
async def list_plans(
    *,
    supabase: Client = Depends(get_supabase_client),
    # current_user: CurrentUserSchema = Depends(deps.get_current_user), # Not strictly needed for public list
    skip: int = 0,
    limit: int = 100,
    show_inactive: bool = False # Admin might want to see inactive plans
) -> Any:
    """
    Retrieve a list of subscription plans.
    Regular users should typically only see active plans. Admins might see all.
    """
    # TODO: Refine access based on user role. If not admin, force show_inactive = False.
    query = supabase.table("planes").select("*")
    if not show_inactive:
        query = query.eq("activo", True)
    
    response = await query.order("precio").range(skip, skip + limit - 1).execute()
    if response.data is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve plans.")
    return response.data

@router.get("/{plan_id}", response_model=PlanResponse)
async def get_plan(
    *,
    plan_id: int,
    supabase: Client = Depends(get_supabase_client)
    # current_user: CurrentUserSchema = Depends(deps.get_current_user) # Not strictly needed for public plan view
) -> Any:
    """
    Get a specific plan by its ID.
    """
    response = await supabase.table("planes").select("*").eq("id", plan_id).maybe_single().execute()
    if not response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plan with ID {plan_id} not found.")
    return response.data

@router.put("/{plan_id}", response_model=PlanResponse)
async def update_plan(
    *,
    plan_id: int,
    plan_in: PlanUpdate,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user) # Placeholder for admin check
) -> Any:
    """
    Update an existing plan.
    (Ideally, admin access required)
    """
    # TODO: Add admin role check
    
    existing_plan_response = await supabase.table("planes").select("id").eq("id", plan_id).maybe_single().execute()
    if not existing_plan_response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plan with ID {plan_id} not found.")

    update_data = plan_in.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update provided.")
    
    update_data["actualizado_en"] = datetime.now(timezone.utc).isoformat()

    response = await supabase.table("planes").update(update_data).eq("id", plan_id).select("*").single().execute()
    if not response.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not update plan with ID {plan_id}.")
    return response.data

@router.delete("/{plan_id}", response_model=PlanResponse) # Returns the deactivated plan
async def deactivate_plan( # Renamed from delete_plan for clarity (soft delete)
    *,
    plan_id: int,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user) # Placeholder for admin check
) -> Any:
    """
    Deactivate a plan (soft delete by setting 'activo' to False).
    (Ideally, admin access required)
    """
    # TODO: Add admin role check
    
    existing_plan_response = await supabase.table("planes").select("id, activo").eq("id", plan_id).maybe_single().execute()
    if not existing_plan_response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plan with ID {plan_id} not found.")
    
    if not existing_plan_response.data.get("activo", True):
        # Plan is already inactive, return current state or a specific message
        # Fetch full plan data for response
        full_plan_response = await supabase.table("planes").select("*").eq("id", plan_id).single().execute()
        if not full_plan_response.data:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plan with ID {plan_id} not found after activity check.")
        return full_plan_response.data


    update_data = {"activo": False, "actualizado_en": datetime.now(timezone.utc).isoformat()}
    response = await supabase.table("planes").update(update_data).eq("id", plan_id).select("*").single().execute()
    
    if not response.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not deactivate plan with ID {plan_id}.")
    return response.data
