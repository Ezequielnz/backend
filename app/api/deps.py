from typing import Dict, Any, Optional

from fastapi import Request, Depends, HTTPException, status
# OAuth2PasswordBearer is removed as token extraction is now handled by middleware
# from fastapi.security import OAuth2PasswordBearer 

from app.db.supabase_client import get_supabase_client, get_table
from supabase import Client as SupabaseClient # For type hinting
from gotrue.types import User as SupabaseAuthUser # For type hinting

# OAuth2 scheme for token authentication (can be kept for OpenAPI docs, but not used for token extraction directly by deps)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login") 


async def get_current_supabase_auth_user(request: Request) -> Optional[SupabaseAuthUser]:
    """
    Retrieves the Supabase authenticated user object from request.state.
    This user object is populated by SupabaseAuthMiddleware.
    Returns None if no authenticated user is found (e.g., token missing or invalid).
    """
    return getattr(request.state, "supabase_user", None)


async def get_current_user(
    request: Request, # Add request to access request.state
    # token: str = Depends(oauth2_scheme) # This is no longer needed here
    supabase_auth_user: Optional[SupabaseAuthUser] = Depends(get_current_supabase_auth_user)
) -> Dict[str, Any]:
    """
    Get the current authenticated user.
    1. Retrieves Supabase auth user from middleware (via get_current_supabase_auth_user).
    2. If Supabase auth user exists, fetches additional profile data from the 'usuarios' table.
    Raises HTTPException 401 if no valid Supabase auth user is found.
    """
    if supabase_auth_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated", # Changed detail message
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # Supabase client for fetching from 'usuarios' table
        # Using get_table for consistency, though get_supabase_client().table() also works
        db_client = get_supabase_client() # Or just use get_table directly

        user_id = supabase_auth_user.id
        # Ensure user_id is a string if your 'id' column in 'usuarios' is text/varchar (UUIDs are typically text)
        # Supabase user.id is usually a UUID string.
        
        user_profile_response = await db_client.table("usuarios").select("*").eq("id", str(user_id)).execute()

        if not user_profile_response.data or len(user_profile_response.data) == 0:
            # User exists in Supabase Auth but not in our public 'usuarios' table.
            # This could be an error state, or you might want to auto-create a profile.
            # For now, we'll return a basic profile based on auth data.
            # Consider logging this situation.
            # fastapi.logger.warning(f"User {user_id} found in Supabase Auth but not in 'usuarios' table.")
            return {
                "id": str(user_id), # Ensure it's a string if that's what your schema expects
                "email": supabase_auth_user.email,
                "rol": getattr(supabase_auth_user, 'role', 'authenticated'), # Supabase user.role
                "aud": supabase_auth_user.aud,
                # Add other fields from supabase_auth_user if needed, or mark as incomplete profile
                "profile_incomplete": True 
            }
        
        user_data = user_profile_response.data[0]
        # Potentially merge or supplement with supabase_auth_user fields if 'usuarios' table is minimal
        # For example, ensure 'email' from auth is preferred if 'usuarios' table might have an older one.
        user_data["email"] = supabase_auth_user.email # Prioritize auth email
        user_data["last_sign_in_at"] = supabase_auth_user.last_sign_in_at.isoformat() if supabase_auth_user.last_sign_in_at else None
        
        return user_data
        
    except Exception as e:
        # fastapi.logger.error(f"Error fetching user profile for {supabase_auth_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, # Or 401 if considered an auth failure extension
            detail="Could not retrieve user profile.",
            headers={"WWW-Authenticate": "Bearer"}, # Keep if 401, optional for 500
        )

async def get_optional_current_user(
    request: Request,
    supabase_auth_user: Optional[SupabaseAuthUser] = Depends(get_current_supabase_auth_user)
) -> Optional[Dict[str, Any]]:
    """
    Get the current authenticated user if a valid token is provided.
    Returns None if no valid token is present.
    Fetches additional profile data from the 'usuarios' table if authenticated.
    """
    if supabase_auth_user is None:
        return None # No authenticated user, return None silently

    # If supabase_auth_user exists, try to get full profile, similar to get_current_user
    try:
        db_client = get_supabase_client()
        user_id = supabase_auth_user.id
        user_profile_response = await db_client.table("usuarios").select("*").eq("id", str(user_id)).execute()

        if not user_profile_response.data or len(user_profile_response.data) == 0:
            return {
                "id": str(user_id),
                "email": supabase_auth_user.email,
                "rol": getattr(supabase_auth_user, 'role', 'authenticated'),
                "aud": supabase_auth_user.aud,
                "profile_incomplete": True
            }
        
        user_data = user_profile_response.data[0]
        user_data["email"] = supabase_auth_user.email
        user_data["last_sign_in_at"] = supabase_auth_user.last_sign_in_at.isoformat() if supabase_auth_user.last_sign_in_at else None
        return user_data
        
    except Exception as e:
        # fastapi.logger.error(f"Error fetching user profile for optional user {supabase_auth_user.id}: {e}")
        # For optional user, if profile fetch fails, might be better to return None or basic auth data
        # instead of raising HTTP 500, depending on desired behavior.
        # Returning basic data for now:
        return {
            "id": str(supabase_auth_user.id),
            "email": supabase_auth_user.email,
            "rol": getattr(supabase_auth_user, 'role', 'authenticated'),
            "aud": supabase_auth_user.aud,
            "profile_fetch_error": True # Indicate that full profile couldn't be retrieved
        }


async def get_current_active_user(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Check if the current user is active
    """
    if current_user.get("activo", True) is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user


async def get_admin_user(current_user: Dict[str, Any] = Depends(get_current_active_user)) -> Dict[str, Any]:
    """
    Check if the current user is an admin
    """
    if current_user.get("rol") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user