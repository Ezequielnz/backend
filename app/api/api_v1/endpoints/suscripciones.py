from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.api.deps import get_current_user_from_request as get_current_user
from app.api.context import BusinessScopedClientDep, ScopedClientContext
from app.schemas.suscripcion import SuscripcionCreate, SuscripcionUpdate, Suscripcion, EstadoSuscripcion
from app.dependencies import PermissionDependency

router = APIRouter()

@router.get("/", response_model=List[Suscripcion],
    dependencies=[Depends(PermissionDependency("puede_ver_productos"))]
)
async def read_subscriptions(
    business_id: str,
    cliente_id: Optional[str] = Query(None, description="Optional client ID to filter subscriptions"),
    servicio_id: Optional[str] = Query(None, description="Optional service ID to filter subscriptions"),
    estado: Optional[EstadoSuscripcion] = Query(None, description="Optional status to filter subscriptions"),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """
    Retrieve subscriptions for a specific business, optionally filtered by client, service or status (requires puede_ver_productos).
    """
    supabase = scoped.client
    
    try:
        query = supabase.table("suscripciones").select("*").eq("negocio_id", business_id)
        
        if cliente_id:
            # Verify the client belongs to the business
            client_response = supabase.table("clientes").select("id").eq("id", cliente_id).eq("negocio_id", business_id).execute()
            if not client_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Cliente no encontrado o no pertenece a este negocio."
                )
            query = query.eq("cliente_id", cliente_id)
            
        if servicio_id:
            # Verify the service belongs to the business
            service_response = supabase.table("servicios").select("id").eq("id", servicio_id).eq("negocio_id", business_id).execute()
            if not service_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Servicio no encontrado o no pertenece a este negocio."
                )
            query = query.eq("servicio_id", servicio_id)
            
        if estado:
            query = query.eq("estado", estado.value)
            
        response = query.execute()
        subscriptions_data = response.data if response.data is not None else []
        
        return [Suscripcion(**item) for item in subscriptions_data]
        
    except Exception as e:
        print(f"Error al obtener suscripciones: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener suscripciones: {str(e)}"
        )

@router.post("/", response_model=Suscripcion, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionDependency("puede_editar_productos"))]
)
async def create_subscription(
    business_id: str,
    subscription_in: SuscripcionCreate,
    current_user: User = Depends(get_current_user),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """
    Create a new subscription for a specific business (requires puede_editar_productos).
    """
    supabase = scoped.client

    try:
        # Verify that the client exists and belongs to the business
        client_response = supabase.table("clientes").select("id").eq("id", subscription_in.cliente_id).eq("negocio_id", business_id).execute()
        if not client_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cliente especificado no encontrado o no pertenece a este negocio.",
            )
            
        # Verify that the service exists and belongs to the business
        service_response = supabase.table("servicios").select("id").eq("id", subscription_in.servicio_id).eq("negocio_id", business_id).execute()
        if not service_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Servicio especificado no encontrado o no pertenece a este negocio.",
            )

        subscription_data = subscription_in.model_dump()
        subscription_data["negocio_id"] = business_id

        response = supabase.table("suscripciones").insert(subscription_data).execute()

        if not response.data:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error al crear la suscripción.",
            )

        return Suscripcion(**response.data[0])

    except HTTPException:
         raise
    except Exception as e:
        print(f"Error al crear suscripción: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear suscripción: {str(e)}"
        )

@router.get("/{subscription_id}", response_model=Suscripcion,
    dependencies=[Depends(PermissionDependency("puede_ver_productos"))]
)
async def read_subscription(
    business_id: str,
    subscription_id: str,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """
    Get a specific subscription by ID for a business (requires puede_ver_productos).
    """
    supabase = scoped.client

    try:
        response = supabase.table("suscripciones").select("*").eq("id", subscription_id).eq("negocio_id", business_id).single().execute()

        return Suscripcion(**response.data)

    except Exception as e:
        if "PostgrestSingleError" in str(e):
             raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Suscripción no encontrada o no pertenece a este negocio.",
            )
        print(f"Error fetching subscription: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener suscripción: {str(e)}",
        )

@router.put("/{subscription_id}", response_model=Suscripcion,
    dependencies=[Depends(PermissionDependency("puede_editar_productos"))]
)
async def update_subscription(
    business_id: str,
    subscription_id: str,
    subscription_update: SuscripcionUpdate,
    current_user: User = Depends(get_current_user),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """
    Update a subscription by ID for a business (requires puede_editar_productos).
    """
    supabase = scoped.client

    try:
        update_data = subscription_update.model_dump(exclude_unset=True)

        # Update the subscription, ensuring it belongs to the correct business
        response = supabase.table("suscripciones").update(update_data).eq("id", subscription_id).eq("negocio_id", business_id).execute()

        if not response.data:
             # Check if subscription exists but doesn't belong to business, or doesn't exist at all
             existing_subscription = supabase.table("suscripciones").select("id").eq("id", subscription_id).execute()
             if existing_subscription.data:
                  raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Suscripción no pertenece a este negocio.",
                 )
             else:
                  raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Suscripción no encontrada.",
                 )
        
        # Fetch the updated subscription to return
        updated_subscription_response = supabase.table("suscripciones").select("*").eq("id", subscription_id).single().execute()
        return Suscripcion(**updated_subscription_response.data)

    except HTTPException:
         raise
    except Exception as e:
        print(f"Error updating subscription: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar suscripción: {str(e)}",
        )

@router.delete("/{subscription_id}",
    dependencies=[Depends(PermissionDependency("puede_editar_productos"))]
)
async def delete_subscription(
    business_id: str,
    subscription_id: str,
    current_user: User = Depends(get_current_user),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
):
    """
    Delete a subscription by ID for a business (requires puede_editar_productos).
    """
    supabase = scoped.client

    try:
        # Check if subscription exists and belongs to the business
        existing_subscription = supabase.table("suscripciones").select("id").eq("id", subscription_id).eq("negocio_id", business_id).execute()
        if not existing_subscription.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Suscripción no encontrada o no pertenece a este negocio.",
            )

        # Delete the subscription
        response = supabase.table("suscripciones").delete().eq("id", subscription_id).eq("negocio_id", business_id).execute()

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error al eliminar la suscripción.",
            )

        return {"message": "Suscripción eliminada exitosamente"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting subscription: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar suscripción: {str(e)}",
        )

@router.patch("/{subscription_id}/estado", response_model=Suscripcion,
    dependencies=[Depends(PermissionDependency("puede_editar_productos"))]
)
async def update_subscription_status(
    business_id: str,
    subscription_id: str,
    estado: EstadoSuscripcion,
    current_user: User = Depends(get_current_user),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """
    Update subscription status (requires puede_editar_productos).
    """
    supabase = scoped.client

    try:
        # Update the subscription status
        response = supabase.table("suscripciones").update({"estado": estado.value}).eq("id", subscription_id).eq("negocio_id", business_id).execute()

        if not response.data:
             raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Suscripción no encontrada o no pertenece a este negocio.",
             )
        
        # Fetch the updated subscription to return
        updated_subscription_response = supabase.table("suscripciones").select("*").eq("id", subscription_id).single().execute()
        return Suscripcion(**updated_subscription_response.data)

    except HTTPException:
         raise
    except Exception as e:
        print(f"Error updating subscription status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar estado de suscripción: {str(e)}",
        ) 

