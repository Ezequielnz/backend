from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from pydantic import ValidationError
from app.api.deps import get_current_user_from_request as get_current_user
from app.api.context import BusinessScopedClientDep, scoped_client_from_request
from app.schemas.servicio import ServicioCreate, ServicioUpdate, Servicio
from app.dependencies import PermissionDependency
import logging
import datetime

router = APIRouter()

# Configure logging
logger = logging.getLogger(__name__)

@router.get("/", response_model=List[Servicio],
    dependencies=[Depends(PermissionDependency("puede_ver_productos")), Depends(BusinessScopedClientDep)]
)
async def read_services(
    business_id: str,
    request: Request,
    category_id: Optional[str] = Query(None, description="Optional category ID to filter services"),
) -> Any:
    """
    Retrieve services for a specific business, optionally filtered by category (requires puede_ver_productos).
    """
    supabase = scoped_client_from_request(request)
    
    try:
        query = supabase.table("servicios").select("*").eq("negocio_id", business_id)
        
        if category_id:
            # Verify the category belongs to the business
            category_response = supabase.table("categorias").select("id").eq("id", category_id).eq("negocio_id", business_id).execute()
            if not category_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Categoría no encontrada o no pertenece a este negocio."
                )
            query = query.eq("categoria_id", category_id)
            
        response = query.execute()
        services_data = response.data if response.data is not None else []
        
        # Validate and serialize each service individually to catch validation errors
        validated_services = []
        for item in services_data:
            try:
                # Ensure required fields are present and handle None values
                if not item.get('id'):
                    logger.warning(f"Skipping service without ID: {item}")
                    continue
                
                # Handle datetime fields properly
                if item.get('creado_en') and isinstance(item['creado_en'], str):
                    # If it's a string, try to parse it
                    try:
                        item['creado_en'] = datetime.datetime.fromisoformat(item['creado_en'].replace('Z', '+00:00'))
                    except ValueError:
                        logger.warning(f"Invalid creado_en format for service {item.get('id')}: {item.get('creado_en')}")
                        # Set a default value
                        item['creado_en'] = datetime.datetime.now()
                
                if item.get('actualizado_en') and isinstance(item['actualizado_en'], str):
                    try:
                        item['actualizado_en'] = datetime.datetime.fromisoformat(item['actualizado_en'].replace('Z', '+00:00'))
                    except ValueError:
                        logger.warning(f"Invalid actualizado_en format for service {item.get('id')}: {item.get('actualizado_en')}")
                        # Set a default value
                        item['actualizado_en'] = datetime.datetime.now()
                
                # Ensure required fields have default values
                if item.get('activo') is None:
                    item['activo'] = True
                
                validated_service = Servicio(**item)
                validated_services.append(validated_service)
                
            except ValidationError as ve:
                logger.error(f"Validation error for service {item.get('id', 'unknown')}: {ve}")
                # Skip invalid services instead of failing the entire request
                continue
            except Exception as e:
                logger.error(f"Error processing service {item.get('id', 'unknown')}: {e}")
                continue
        
        return validated_services
        
    except HTTPException:
        # Re-raise HTTP exceptions as they are expected
        raise
    except Exception as e:
        logger.error(f"Error al obtener servicios: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener servicios: {str(e)}"
        )

@router.post("/", response_model=Servicio, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionDependency("puede_editar_productos")), Depends(BusinessScopedClientDep)]
)
async def create_service(
    business_id: str,
    service_in: ServicioCreate,
    request: Request,
) -> Any:
    """
    Create a new service for a specific business (requires puede_editar_productos).
    """
    supabase = scoped_client_from_request(request)

    try:
        # Verify that the category exists and belongs to the business (only if categoria_id is provided)
        if service_in.categoria_id:
            category_response = supabase.table("categorias").select("id").eq("id", service_in.categoria_id).eq("negocio_id", business_id).execute()
            if not category_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Categoría especificada no encontrada o no pertenece a este negocio.",
                )

        service_data = service_in.model_dump()
        service_data["negocio_id"] = business_id

        response = supabase.table("servicios").insert(service_data).execute()

        if not response.data:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error al crear el servicio.",
            )

        return Servicio(**response.data[0])

    except HTTPException:
         raise
    except Exception as e:
        print(f"Error al crear servicio: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear servicio: {str(e)}"
        )

@router.get("/{service_id}", response_model=Servicio,
    dependencies=[Depends(PermissionDependency("puede_ver_productos")), Depends(BusinessScopedClientDep)]
)
async def read_service(
    business_id: str,
    service_id: str,
    request: Request,
) -> Any:
    """
    Get a specific service by ID for a business (requires puede_ver_productos).
    """
    supabase = scoped_client_from_request(request)

    try:
        response = supabase.table("servicios").select("*").eq("id", service_id).eq("negocio_id", business_id).single().execute()

        return Servicio(**response.data)

    except Exception as e:
        if "PostgrestSingleError" in str(e):
             raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Servicio no encontrado o no pertenece a este negocio.",
            )
        print(f"Error fetching service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener servicio: {str(e)}",
        )

@router.put("/{service_id}", response_model=Servicio,
    dependencies=[Depends(PermissionDependency("puede_editar_productos")), Depends(BusinessScopedClientDep)]
)
async def update_service(
    business_id: str,
    service_id: str,
    service_update: ServicioUpdate,
    request: Request,
) -> Any:
    """
    Update a service by ID for a business (requires puede_editar_productos).
    """
    supabase = scoped_client_from_request(request)

    try:
        update_data = service_update.model_dump(exclude_unset=True)
        
        # If category_id is being updated, verify it exists and belongs to the business
        if "categoria_id" in update_data and update_data["categoria_id"] is not None:
             category_response = supabase.table("categorias").select("id").eq("id", update_data["categoria_id"]).eq("negocio_id", business_id).execute()
             if not category_response.data:
                  raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Nueva categoría especificada no encontrada o no pertenece a este negocio.",
                 )

        # Update the service, ensuring it belongs to the correct business
        response = supabase.table("servicios").update(update_data).eq("id", service_id).eq("negocio_id", business_id).execute()

        if not response.data:
             # Check if service exists but doesn't belong to business, or doesn't exist at all
             existing_service = supabase.table("servicios").select("id").eq("id", service_id).execute()
             if existing_service.data:
                  raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Servicio no pertenece a este negocio.",
                 )
             else:
                  raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Servicio no encontrado.",
                 )
        
        # Fetch the updated service to return
        updated_service_response = supabase.table("servicios").select("*").eq("id", service_id).single().execute()
        return Servicio(**updated_service_response.data)

    except HTTPException:
         raise
    except Exception as e:
        print(f"Error updating service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar servicio: {str(e)}",
        )

@router.delete("/{service_id}",
    dependencies=[Depends(PermissionDependency("puede_editar_productos")), Depends(BusinessScopedClientDep)]
)
async def delete_service(
    business_id: str,
    service_id: str,
    request: Request,
):
    """
    Delete a service by ID for a business (requires puede_editar_productos).
    """
    supabase = scoped_client_from_request(request)

    try:
        # Check if service exists and belongs to the business
        existing_service = supabase.table("servicios").select("id").eq("id", service_id).eq("negocio_id", business_id).execute()
        if not existing_service.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Servicio no encontrado o no pertenece a este negocio.",
            )

        # Delete the service
        response = supabase.table("servicios").delete().eq("id", service_id).eq("negocio_id", business_id).execute()

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error al eliminar el servicio.",
            )

        return {"message": "Servicio eliminado exitosamente"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar servicio: {str(e)}",
        ) 