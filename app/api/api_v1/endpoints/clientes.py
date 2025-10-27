from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.context import BusinessScopedClientDep, ScopedClientContext
from app.api.deps import get_current_user
from app.dependencies import PermissionDependency
from app.schemas.cliente import Cliente, ClienteCreate, ClienteUpdate
from app.types.auth import User

router = APIRouter()


@router.get(
    "/",
    response_model=List[Cliente],
    dependencies=[Depends(PermissionDependency("clientes", "ver"))],
)
@router.get(
    "",
    response_model=List[Cliente],  # Ruta sin barra final
    dependencies=[Depends(PermissionDependency("clientes", "ver"))],
)
async def read_clientes(
    business_id: str,
    q: Optional[str] = Query(None, description="Busqueda por nombre, apellido, email o documento"),
    documento_tipo: Optional[str] = Query(None, description="Filtrar por tipo de documento"),
    limit: int = Query(10, ge=1, le=100, description="Numero maximo de resultados"),
    offset: int = Query(0, ge=0, description="Numero de resultados a omitir"),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """List customers for a business with optional filtering and pagination."""

    supabase = scoped.client

    try:
        query = supabase.table("clientes").select("*")
        query = query.eq("negocio_id", business_id)

        if q:
            query = query.ilike("nombre", f"%{q}%")

        if documento_tipo:
            query = query.eq("documento_tipo", documento_tipo)

        query = query.range(offset, offset + limit - 1)

        response = query.execute()
        return response.data

    except Exception as exc:  # pragma: no cover - propagates as HTTP error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching clients: {exc}",
        ) from exc


@router.get(
    "/{cliente_id}",
    response_model=Cliente,
    dependencies=[Depends(PermissionDependency("clientes", "ver"))],
)
async def read_cliente(
    business_id: str,
    cliente_id: str,
    current_user: User = Depends(get_current_user),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """Retrieve a single customer by ID."""

    supabase = scoped.client

    try:
        response = (
            supabase.table("clientes")
            .select("*")
            .eq("id", cliente_id)
            .eq("negocio_id", business_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Client not found",
            )

        return response.data[0]

    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - propagates as HTTP error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching client: {exc}",
        ) from exc


@router.post(
    "/",
    response_model=Cliente,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionDependency("clientes", "editar"))],
)
@router.post(
    "",
    response_model=Cliente,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionDependency("clientes", "editar"))],
)
async def create_cliente(
    business_id: str,
    cliente: ClienteCreate,
    current_user: User = Depends(get_current_user),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """Create a new customer for the given business."""

    supabase = scoped.client

    try:
        payload = cliente.dict()
        payload["negocio_id"] = business_id

        response = supabase.table("clientes").insert(payload).execute()

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create client",
            )

        return response.data[0]

    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - propagates as HTTP error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating client: {exc}",
        ) from exc


@router.put(
    "/{cliente_id}",
    response_model=Cliente,
    dependencies=[Depends(PermissionDependency("clientes", "editar"))],
)
async def update_cliente(
    business_id: str,
    cliente_id: str,
    cliente: ClienteUpdate,
    current_user: User = Depends(get_current_user),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """Update a customer record."""

    supabase = scoped.client

    try:
        update_data = {key: value for key, value in cliente.dict().items() if value is not None}

        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No data provided for update",
            )

        response = (
            supabase.table("clientes")
            .update(update_data)
            .eq("id", cliente_id)
            .eq("negocio_id", business_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Client not found or no changes made",
            )

        return response.data[0]

    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - propagates as HTTP error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating client: {exc}",
        ) from exc


@router.delete(
    "/{cliente_id}",
    dependencies=[Depends(PermissionDependency("clientes", "eliminar"))],
)
async def delete_cliente(
    business_id: str,
    cliente_id: str,
    current_user: User = Depends(get_current_user),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """Delete a customer if there are no dependent sales."""

    supabase = scoped.client

    try:
        ventas_response = (
            supabase.table("ventas")
            .select("id")
            .eq("cliente_id", cliente_id)
            .limit(1)
            .execute()
        )
        if ventas_response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se puede eliminar el cliente porque tiene ventas asociadas.",
            )

        response = (
            supabase.table("clientes")
            .delete()
            .eq("id", cliente_id)
            .eq("negocio_id", business_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Client not found",
            )

        return {"message": "Client deleted successfully"}

    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - propagates as HTTP error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting client: {exc}",
        ) from exc
