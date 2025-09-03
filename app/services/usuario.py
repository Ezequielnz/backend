from app.db.supabase_client import get_table
from app.models.supabase_models import Usuario as UsuarioModel
from app.schemas.usuario import UsuarioCreate, UsuarioUpdate
from typing import cast


async def get(id: int) -> dict[str, object] | None:
    """
    Get a single user by ID.
    """
    return await UsuarioModel.get_by_id(id)


async def get_by_email(email: str) -> dict[str, object] | None:
    """
    Get a single user by email.
    """
    resp_obj = (
        get_table(UsuarioModel.table_name())
        .select("*")
        .eq("email", email)
        .execute()
    )
    rows = cast(list[dict[str, object]], getattr(resp_obj, "data", []) or [])
    return rows[0] if rows else None


async def get_multi(skip: int = 0, limit: int = 100) -> list[dict[str, object]]:
    """
    Get multiple users.
    """
    users = await UsuarioModel.get_all()
    return users[skip : skip + limit]


async def create(*, obj_in: UsuarioCreate) -> dict[str, object] | None:
    """
    Create a new user.
    """
    from datetime import datetime
    
    user_data = obj_in.model_dump()

    user_data["creado_en"] = datetime.now().isoformat()
    
    return await UsuarioModel.create(user_data)


async def update(*, id: int, obj_in: UsuarioUpdate | dict[str, object]) -> dict[str, object] | None:
    """
    Update a user.
    """
    if isinstance(obj_in, dict):
        update_data = obj_in
    else:
        update_data = obj_in.model_dump(exclude_unset=True)
    
    return await UsuarioModel.update(id, update_data)


async def delete(*, id: int) -> dict[str, object] | None:
    """
    Delete a user.
    """
    return await UsuarioModel.delete(id)