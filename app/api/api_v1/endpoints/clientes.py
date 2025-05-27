from typing import List, Any

from fastapi import APIRouter, Depends, HTTPException, status, Response
from supabase.client import Client # For type hinting Supabase client

from app.db.supabase_client import get_supabase_client
from app.api import deps
from app.schemas.usuario import Usuario as CurrentUserSchema # For current_user type
from app.schemas.cliente import Cliente, ClienteCreate, ClienteUpdate # Client schemas

router = APIRouter()

@router.post("/", response_model=Cliente, status_code=status.HTTP_201_CREATED)
async def create_client(
    *,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
    client_in: ClienteCreate
) -> Any:
    """
    Create a new client. The client will be associated with the current authenticated user.
    """
    # Prepare data for insertion, including the owner's ID
    client_data = client_in.model_dump()
    client_data["empleado_id"] = current_user.id # Assuming current_user.id is the UUID string

    # It's good practice to check if a client with similar unique identifiers already exists for this user
    # For example, if 'documento_numero' should be unique per user:
    if client_in.documento_numero:
        existing_doc_response = await supabase.table("clientes").select("id") \
            .eq("documento_numero", client_in.documento_numero) \
            .eq("empleado_id", current_user.id) \
            .execute()
        if existing_doc_response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A client with this document number already exists for this user.",
            )

    response = await supabase.table("clientes").insert(client_data).select("*").single().execute()

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create client.",
        )
    return response.data

@router.get("/", response_model=List[Cliente])
async def list_clients(
    *,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
    skip: int = 0,
    limit: int = 100
) -> Any:
    """
    Retrieve a list of clients associated with the current authenticated user.
    """
    response = await supabase.table("clientes").select("*") \
        .eq("empleado_id", current_user.id) \
        .range(skip, skip + limit - 1) \
        .execute()
    
    # response.data will be an empty list if no clients, which is fine.
    # Only raise error if supabase itself had an issue (though client usually handles this)
    # For robustness, one might check for specific Supabase errors if needed.
    return response.data

@router.get("/{cliente_id}", response_model=Cliente)
async def get_client(
    *,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
    cliente_id: int
) -> Any:
    """
    Get a specific client by its ID.
    Ensures the client belongs to the authenticated user.
    """
    response = await supabase.table("clientes").select("*").eq("id", cliente_id).maybe_single().execute()

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client with ID {cliente_id} not found.",
        )
    
    client_data = response.data
    if client_data.get("empleado_id") != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this client.",
        )
    return client_data

@router.put("/{cliente_id}", response_model=Cliente)
async def update_client(
    *,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
    cliente_id: int,
    client_in: ClienteUpdate
) -> Any:
    """
    Update an existing client.
    Ensures the client belongs to the authenticated user.
    `empleado_id` cannot be updated.
    """
    # First, verify the client exists and belongs to the user
    existing_client_response = await supabase.table("clientes").select("*").eq("id", cliente_id).maybe_single().execute()
    if not existing_client_response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client with ID {cliente_id} not found.",
        )
    
    if existing_client_response.data.get("empleado_id") != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify this client.",
        )

    update_data = client_in.model_dump(exclude_unset=True) # For partial updates
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update provided.",
        )

    # Ensure 'empleado_id' is not in the update_data, as it should not be changed
    if "empleado_id" in update_data:
        del update_data["empleado_id"]

    response = await supabase.table("clientes").update(update_data).eq("id", cliente_id).select("*").single().execute()

    if not response.data:
        # This might happen if RLS prevents update or other issues.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not update client with ID {cliente_id}.",
        )
    return response.data

@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    *,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
    cliente_id: int
) -> Response:
    """
    Delete a client.
    Ensures the client belongs to the authenticated user.
    Performs a hard delete.
    """
    # First, verify the client exists and belongs to the user
    existing_client_response = await supabase.table("clientes").select("id, empleado_id").eq("id", cliente_id).maybe_single().execute()
    if not existing_client_response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client with ID {cliente_id} not found.",
        )
    
    if existing_client_response.data.get("empleado_id") != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this client.",
        )

    # Perform the delete operation
    # Supabase delete() does not return data by default unless .select() is chained.
    # We only care about success or failure here.
    delete_op = await supabase.table("clientes").delete().eq("id", cliente_id).execute()
    
    # The Supabase Python client typically raises an error if the delete fails due to RLS or other DB constraints.
    # If delete_op.data is empty after a delete, it usually means the record was not found or RLS prevented it.
    # However, we've already checked for existence and ownership.
    # If no exception is raised by the client, we assume success.
    # A more robust check might involve looking at delete_op.count if available and > 0.
    # For now, if no error, return 204.

    return Response(status_code=status.HTTP_204_NO_CONTENT)
