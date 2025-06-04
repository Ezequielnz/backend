from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from app.api.deps import get_current_user
from app.db.supabase_client import get_supabase_client
from app.schemas.cliente import ClienteCreate, ClienteUpdate, Cliente, ClienteSearch
from app.types.auth import User

router = APIRouter()

@router.get("/", response_model=List[Cliente])
async def read_clientes(
    business_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    q: Optional[str] = Query(None, description="Búsqueda por nombre, apellido, email o documento"),
    documento_tipo: Optional[str] = Query(None, description="Filtrar por tipo de documento"),
    limit: int = Query(10, ge=1, le=100, description="Número máximo de resultados"),
    offset: int = Query(0, ge=0, description="Número de resultados a omitir")
) -> Any:
    """
    Retrieve clients for a business with optional filtering and pagination.
    RLS policies handle permission checking automatically.
    """
    supabase = get_supabase_client()

    try:
        # Build query
        query = supabase.table("clientes").select("*").eq("negocio_id", business_id)
        
        # Apply filters
        if q:
            # Search in multiple fields
            query = query.or_(f"nombre.ilike.%{q}%,apellido.ilike.%{q}%,email.ilike.%{q}%,documento_numero.ilike.%{q}%")
        
        if documento_tipo:
            query = query.eq("documento_tipo", documento_tipo)
        
        # Apply pagination
        query = query.range(offset, offset + limit - 1)
        
        # Execute query
        response = query.execute()
        
        return response.data
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching clients: {str(e)}"
        )

@router.get("/{cliente_id}", response_model=Cliente)
async def read_cliente(
    business_id: str,
    cliente_id: str,
    request: Request,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get a specific client by ID for a business.
    RLS policies handle permission checking automatically.
    """
    supabase = get_supabase_client()

    try:
        response = supabase.table("clientes").select("*").eq("id", cliente_id).eq("negocio_id", business_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Client not found"
            )
        
        return response.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching client: {str(e)}"
        )

@router.post("/", response_model=Cliente, status_code=status.HTTP_201_CREATED)
async def create_cliente(
    business_id: str,
    cliente: ClienteCreate,
    request: Request,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Create a new client for a business.
    RLS policies handle permission checking automatically.
    """
    supabase = get_supabase_client()

    try:
        # Prepare client data
        cliente_data = cliente.dict()
        cliente_data["negocio_id"] = business_id
        
        # Insert client
        response = supabase.table("clientes").insert(cliente_data).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create client"
            )
        
        return response.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating client: {str(e)}"
        )

@router.put("/{cliente_id}", response_model=Cliente)
async def update_cliente(
    business_id: str,
    cliente_id: str,
    cliente: ClienteUpdate,
    request: Request,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Update a client by ID for a business.
    RLS policies handle permission checking automatically.
    """
    supabase = get_supabase_client()

    try:
        # Prepare update data (exclude None values)
        update_data = {k: v for k, v in cliente.dict().items() if v is not None}
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No data provided for update"
            )
        
        # Update client
        response = supabase.table("clientes").update(update_data).eq("id", cliente_id).eq("negocio_id", business_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Client not found or no changes made"
            )
        
        return response.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating client: {str(e)}"
        )

@router.delete("/{cliente_id}")
async def delete_cliente(
    business_id: str,
    cliente_id: str,
    request: Request,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Delete a client by ID for a business.
    RLS policies handle permission checking automatically.
    """
    supabase = get_supabase_client()

    try:
        # Check if client has associated sales
        ventas_response = supabase.table("ventas").select("id").eq("cliente_id", cliente_id).limit(1).execute()
        if ventas_response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se puede eliminar el cliente porque tiene ventas asociadas."
            )

        # Delete client
        response = supabase.table("clientes").delete().eq("id", cliente_id).eq("negocio_id", business_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Client not found"
            )
        
        return {"message": "Client deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting client: {str(e)}"
        ) 