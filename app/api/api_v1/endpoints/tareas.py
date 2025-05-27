from typing import List, Any, Optional
from datetime import datetime, date, timezone

from fastapi import APIRouter, HTTPException, status, Depends, Response
from supabase.client import Client

# Import dependencies and schemas
from app.api import deps
from app.db.supabase_client import get_supabase_client
from app.schemas.usuario import Usuario as CurrentUserSchema # To type hint current_user
from app.schemas.tarea import TareaCreate, TareaUpdate, TareaResponse, TareaListParams

router = APIRouter()

# Helper to validate if a user ID (UUID string) exists in the 'usuarios' table
async def _validate_user_exists(user_id: str, supabase: Client, error_msg_prefix: str):
    if user_id: # Only validate if an ID is provided
        user_response = await supabase.table("usuarios").select("id").eq("id", user_id).maybe_single().execute()
        if not user_response.data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{error_msg_prefix}: User with ID '{user_id}' not found.")

@router.post("/", response_model=TareaResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    *,
    task_in: TareaCreate,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user)
) -> Any:
    """
    Create a new task.
    `creado_por_id` is automatically set to the authenticated user's ID.
    `asignado_id` can be provided to assign the task; this user must exist.
    """
    if task_in.asignado_id:
        await _validate_user_exists(task_in.asignado_id, supabase, "Validation for 'asignado_id' failed")

    task_data = task_in.model_dump()
    task_data["creado_por"] = str(current_user.id) # Map to 'creado_por' in DB, ensure string UUID
    if task_in.asignado_id:
        task_data["asignado_id"] = str(task_in.asignado_id) # Ensure string UUID
    
    # Map schema field 'fecha_fin' to DB field 'fecha_fin'
    # Model has 'creado_en' and 'actualizado_en' which are auto-handled by DB or Supabase client
    
    response = await supabase.table("tareas").insert(task_data).select("*").single().execute()

    if not response.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create task.")
    
    # Adapt response data to TareaResponse schema field names if necessary
    # Specifically: 'creado_por' from DB to 'creado_por_id' in response
    db_task = response.data
    return TareaResponse(
        id=db_task["id"],
        titulo=db_task["titulo"],
        descripcion=db_task.get("descripcion"),
        fecha_fin=db_task.get("fecha_fin"), # Already date or None from DB
        estado=db_task["estado"],
        prioridad=db_task.get("prioridad"),
        creado_por_id=str(db_task["creado_por"]), # Ensure str for UUID
        asignado_id=str(db_task["asignado_id"]) if db_task.get("asignado_id") else None, # Ensure str for UUID
        creado_en=db_task["creado_en"],
        actualizado_en=db_task.get("actualizado_en")
    )


@router.get("/", response_model=List[TareaResponse])
async def list_tasks(
    *,
    params: TareaListParams = Depends(), # Use the Pydantic model for query params
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
    skip: int = 0,
    limit: int = 100
) -> Any:
    """
    Get a list of tasks.
    Default: Lists tasks created by or assigned to the authenticated user.
    Filters can be applied for: asignado_id, creado_por_id, estado, fecha_fin range, prioridad.
    """
    query = supabase.table("tareas").select("*")

    # Default filtering: tasks created by or assigned to the current user
    if params.asignado_id is None and params.creado_por_id is None:
         query = query.or_(f"creado_por.eq.{current_user.id},asignado_id.eq.{current_user.id}")
    
    if params.asignado_id:
        query = query.eq("asignado_id", str(params.asignado_id))
    if params.creado_por_id:
        query = query.eq("creado_por", str(params.creado_por_id))
    if params.estado:
        query = query.eq("estado", params.estado)
    if params.prioridad:
        query = query.eq("prioridad", params.prioridad)
    if params.fecha_fin_desde:
        query = query.gte("fecha_fin", params.fecha_fin_desde.isoformat())
    if params.fecha_fin_hasta:
        query = query.lte("fecha_fin", params.fecha_fin_hasta.isoformat())

    response = await query.order("creado_en", desc=True).range(skip, limit -1 + skip).execute()

    if response.data is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching tasks.")

    # Adapt list of DB tasks to list of TareaResponse
    return [
        TareaResponse(
            id=t["id"],
            titulo=t["titulo"],
            descripcion=t.get("descripcion"),
            fecha_fin=t.get("fecha_fin"),
            estado=t["estado"],
            prioridad=t.get("prioridad"),
            creado_por_id=str(t["creado_por"]),
            asignado_id=str(t["asignado_id"]) if t.get("asignado_id") else None,
            creado_en=t["creado_en"],
            actualizado_en=t.get("actualizado_en")
        ) for t in response.data
    ]


@router.get("/{tarea_id}", response_model=TareaResponse)
async def get_task(
    *,
    tarea_id: int,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user)
) -> Any:
    """
    Get a specific task by ID.
    User must be the creator or assignee of the task.
    """
    response = await supabase.table("tareas").select("*").eq("id", tarea_id).maybe_single().execute()

    if not response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task with ID {tarea_id} not found.")
    
    task_db = response.data
    # Ensure current_user.id is string for comparison with string UUIDs from DB
    current_user_id_str = str(current_user.id)
    
    is_creator = str(task_db.get("creado_por")) == current_user_id_str
    is_assignee = task_db.get("asignado_id") is not None and str(task_db.get("asignado_id")) == current_user_id_str

    if not (is_creator or is_assignee):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this task.")

    return TareaResponse(
        id=task_db["id"],
        titulo=task_db["titulo"],
        descripcion=task_db.get("descripcion"),
        fecha_fin=task_db.get("fecha_fin"),
        estado=task_db["estado"],
        prioridad=task_db.get("prioridad"),
        creado_por_id=str(task_db["creado_por"]),
        asignado_id=str(task_db["asignado_id"]) if task_db.get("asignado_id") else None,
        creado_en=task_db["creado_en"],
        actualizado_en=task_db.get("actualizado_en")
    )


@router.put("/{tarea_id}", response_model=TareaResponse)
async def update_task(
    *,
    tarea_id: int,
    task_in: TareaUpdate,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user)
) -> Any:
    """
    Update an existing task.
    User must be the creator or assignee. `creado_por_id` cannot be changed.
    """
    existing_task_response = await supabase.table("tareas").select("*").eq("id", tarea_id).maybe_single().execute()
    if not existing_task_response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task with ID {tarea_id} not found.")
    
    task_db = existing_task_response.data
    current_user_id_str = str(current_user.id)

    is_creator = str(task_db.get("creado_por")) == current_user_id_str
    is_assignee = task_db.get("asignado_id") is not None and str(task_db.get("asignado_id")) == current_user_id_str

    if not (is_creator or is_assignee):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to update this task.")

    if task_in.asignado_id:
        await _validate_user_exists(task_in.asignado_id, supabase, "Validation for new 'asignado_id' failed")

    update_data = task_in.model_dump(exclude_unset=True)
    # Ensure 'creado_por' or 'creado_por_id' is not in update_data
    update_data.pop("creado_por", None)
    update_data.pop("creado_por_id", None)
    
    # Map schema field 'fecha_fin' to DB field 'fecha_fin' if present
    # 'actualizado_en' should be set by DB trigger ideally, or manually:
    update_data["actualizado_en"] = datetime.now(timezone.utc).isoformat()

    if not update_data:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update provided.")

    response = await supabase.table("tareas").update(update_data).eq("id", tarea_id).select("*").single().execute()

    if not response.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not update task with ID {tarea_id}.")

    updated_db_task = response.data
    return TareaResponse(
        id=updated_db_task["id"],
        titulo=updated_db_task["titulo"],
        descripcion=updated_db_task.get("descripcion"),
        fecha_fin=updated_db_task.get("fecha_fin"),
        estado=updated_db_task["estado"],
        prioridad=updated_db_task.get("prioridad"),
        creado_por_id=str(updated_db_task["creado_por"]),
        asignado_id=str(updated_db_task["asignado_id"]) if updated_db_task.get("asignado_id") else None,
        creado_en=updated_db_task["creado_en"],
        actualizado_en=updated_db_task.get("actualizado_en")
    )


@router.delete("/{tarea_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    *,
    tarea_id: int,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user)
) -> Response:
    """
    Delete a task. Only the creator can delete.
    """
    task_to_delete_response = await supabase.table("tareas").select("id, creado_por").eq("id", tarea_id).maybe_single().execute()
    if not task_to_delete_response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task with ID {tarea_id} not found.")

    if str(task_to_delete_response.data.get("creado_por")) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to delete this task. Only the creator can delete.")

    await supabase.table("tareas").delete().eq("id", tarea_id).execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Remove old placeholder endpoints if they were not already replaced.
# The following lines assume the old /calendario and /empleado/{empleado_id} are no longer needed.
# If they are, they should be updated similarly or kept if they serve a different purpose.
# Based on the new CRUD structure, they seem redundant unless /calendario had specific aggregate logic.

# @router.get("/calendario") ...
# @router.get("/empleado/{empleado_id}") ...