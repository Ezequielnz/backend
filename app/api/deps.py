from typing import Dict, Any, Optional, TypedDict
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.db.supabase_client import get_supabase_client

class UserData(TypedDict):
    id: str
    email: str
    rol: str
    activo: bool

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserData:
    """
    Get the current authenticated user from the token.
    
    Args:
        token: JWT token from OAuth2 scheme
        
    Returns:
        UserData: User information including id, email, role and active status
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    supabase = get_supabase_client()
    
    try:
        auth_response = supabase.auth.get_user(token)
        
        if not auth_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user_id = auth_response.user.id
        user_response = supabase.table("usuarios").select("*").eq("id", user_id).execute()
        
        if not user_response.data:
            return {
                "id": user_id,
                "email": auth_response.user.email,
                "rol": "usuario",
                "activo": True
            }
            
        return user_response.data[0]
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_active_user(
    current_user: UserData = Depends(get_current_user)
) -> UserData:
    """
    Check if the current user is active.
    
    Args:
        current_user: User data from get_current_user dependency
        
    Returns:
        UserData: User information if active
        
    Raises:
        HTTPException: If user is inactive
    """
    if not current_user.get("activo", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user

async def get_admin_user(
    current_user: UserData = Depends(get_current_active_user)
) -> UserData:
    """
    Check if the current user is an admin.
    
    Args:
        current_user: User data from get_current_active_user dependency
        
    Returns:
        UserData: User information if admin
        
    Raises:
        HTTPException: If user is not admin
    """
    if current_user.get("rol") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user