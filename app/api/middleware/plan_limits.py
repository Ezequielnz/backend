from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseFunction
from starlette.requests import Request
from starlette.responses import Response
from fastapi.logger import logger # Using FastAPI's logger
import logging # Or standard logging

from app.db.supabase_client import get_supabase_client # To potentially fetch subscription
# from app.schemas.suscripcion import SuscripcionResponse # If we were to parse a full subscription

# Placeholder for where active subscription might be stored or how to fetch it
# In a full system, another middleware might populate request.state.active_subscription,
# or this middleware could fetch it if needed for specific paths.

class PlanLimitsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseFunction) -> Response:
        
        # This middleware is a placeholder. In a real application, it would:
        # 1. Identify if the current request path needs plan limit checks.
        #    (e.g., creating a new project, adding a team member, etc.)
        #    For now, it runs on all requests after it in the stack.
        #
        # 2. Get the authenticated user (already done by SupabaseAuthMiddleware if it runs before this)
        current_supabase_user = getattr(request.state, "supabase_user", None)

        if current_supabase_user:
            user_id = current_supabase_user.id
            logger.info(f"PlanLimitsMiddleware: Processing request for user {user_id}. Path: {request.url.path}")

            # --- Placeholder for fetching active subscription and checking limits ---
            # In a real scenario, you might fetch the user's active subscription here
            # if it's not already populated in request.state by another middleware.
            # Example:
            # try:
            #     supabase = get_supabase_client() # Get a Supabase client instance
            #     active_sub_response = await supabase.table("suscripciones") \
            #         .select("*, plan:planes(*)") \
            #         .eq("usuario_id", str(user_id)) \
            #         .eq("estado", "activa") \
            #         .maybe_single() \
            #         .execute()
            #     
            #     if active_sub_response.data:
            #         active_subscription = active_sub_response.data # This would be a dict
            #         logger.info(f"User {user_id} has active subscription: Plan '{active_subscription.get('plan', {}).get('nombre', 'N/A')}'")
            #         # plan_limits = active_subscription.get('plan', {}).get('limites', {})
            #         # Here, you would compare current resource usage against plan_limits
            #         # e.g., if request.url.path == "/api/v1/projects/" and request.method == "POST":
            #         #     current_project_count = await get_user_project_count(supabase, user_id)
            #         #     max_projects = plan_limits.get("max_proyectos", float('inf'))
            #         #     if current_project_count >= max_projects:
            #         #         logger.warning(f"User {user_id} exceeded project limit ({max_projects}).")
            #         #         # Return HTTPException(status_code=403, detail="Project limit reached for your current plan.")
            #         #         # For this placeholder, we just log and proceed.
            #     else:
            #         logger.info(f"User {user_id} has no active subscription found.")
            #         # Handle cases for users without active subscriptions (e.g., free plan, or block access)
            #
            # except Exception as e:
            #     logger.error(f"PlanLimitsMiddleware: Error fetching subscription for user {user_id}: {e}")
            #
            # For this placeholder task, we are just logging and not performing actual checks or raising exceptions.
            logger.info(f"PlanLimitsMiddleware: Placeholder - Actual limit checking for user {user_id} would occur here.")

        else:
            # No authenticated user found in request.state (e.g., public route, or SupabaseAuthMiddleware didn't run/set it)
            # logger.info(f"PlanLimitsMiddleware: No authenticated user found for path {request.url.path}.")
            pass # Do nothing for unauthenticated users or if user state is not set

        response = await call_next(request)
        return response
