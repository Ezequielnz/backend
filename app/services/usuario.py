from typing import Any, Dict, List, Optional, Union
from sqlalchemy.orm import Session

from app.db.supabase_client import get_table
from app.models.supabase_models import Usuario as UsuarioModel
from app.schemas.usuario import UsuarioCreate, UsuarioUpdate


async def get(id: int) -> Optional[Dict[str, Any]]:
    """
    Get a single user by ID.
    """
    return await UsuarioModel.get_by_id(id)


async def get_by_email(email: str) -> Optional[Dict[str, Any]]:
    """
    Get a single user by email.
    """
    response = get_table(UsuarioModel.table_name()).select("*").eq("email", email).execute()
    data = response.data
    return data[0] if data else None


async def get_multi(skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get multiple users.
    """
    users = await UsuarioModel.get_all()
    return users[skip : skip + limit]


async def create(*, obj_in: UsuarioCreate) -> Dict[str, Any]:
    """
    Create a new user.
    """
    from datetime import datetime
    
    user_data = obj_in.dict()
    user_data["creado_en"] = datetime.now().isoformat()
    
    return await UsuarioModel.create(user_data)


async def update(*, id: int, obj_in: Union[UsuarioUpdate, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Update a user.
    """
    if isinstance(obj_in, dict):
        update_data = obj_in
    else:
        update_data = obj_in.dict(exclude_unset=True)
    
    return await UsuarioModel.update(id, update_data)


async def delete(*, id: int) -> Dict[str, Any]:
    """
    Delete a user.
    """
    return await UsuarioModel.delete(id) 