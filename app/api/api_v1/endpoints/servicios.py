from app.api.context import ScopedClientContext
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
    dependencies=[Depends(PermissionDependency("puede_ver_productos"))]
)
async def read_services(
    business_id: str,
    request: Request,
    category_id: Optional[str] = Query(None, description="Optional category ID to filter services"),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep)
) -> Any:
    """
    Retrieve services for a specific business, optionally filtered by category.
    """
    supabase = scoped.client
    context = scoped.context
    
    settings = context.branch_settings or {}
    servicios_modo = settings.get("servicios_modo", "centralizado")
    
    try:
        # We always query the base "servicios" table
        if servicios_modo == "por_sucursal" and context.branch_id:
            # We fetch all services but also join their branch specific info
            query = supabase.table("servicios").select("*, servicio_sucursal!inner(precio, estado, sucursal_id)").eq("negocio_id", business_id).eq("servicio_sucursal.sucursal_id", context.branch_id)
        else:
            query = supabase.table("servicios").select("*").eq("negocio_id", business_id)
            
        if category_id:
            query = query.eq("categoria_id", category_id)
            
        response = query.execute()
        services_data = response.data if response.data is not None else []
        
        validated_services = []
        for item in services_data:
            try:
                # If por_sucursal, overwrite the base service fields with the branch specific ones
                if servicios_modo == "por_sucursal" and context.branch_id and "servicio_sucursal" in item:
                    branch_info = item.pop("servicio_sucursal")
                    if isinstance(branch_info, list) and len(branch_info) > 0:
                        branch_info = branch_info[0]
                    if isinstance(branch_info, dict):
                        if "precio" in branch_info:
                            item["precio"] = branch_info["precio"]
                        if "estado" in branch_info:
                            item["activo"] = (branch_info["estado"] == "activo")

                if not item.get('id'):
                    continue
                
                # Handling datetime...
                if item.get('creado_en') and isinstance(item['creado_en'], str):
                    try:
                        item['creado_en'] = datetime.datetime.fromisoformat(item['creado_en'].replace('Z', '+00:00'))
                    except ValueError:
                        item['creado_en'] = datetime.datetime.now()
                
                if item.get('actualizado_en') and isinstance(item['actualizado_en'], str):
                    try:
                        item['actualizado_en'] = datetime.datetime.fromisoformat(item['actualizado_en'].replace('Z', '+00:00'))
                    except ValueError:
                        item['actualizado_en'] = datetime.datetime.now()
                
                if item.get('estado') is not None:
                    item['activo'] = (item['estado'] == 'activo')
                elif item.get('activo') is None:
                    item['activo'] = True
                
                validated_services.append(Servicio(**item))
            except Exception as e:
                logger.error(f"Error processing service: {e}")
                continue
        
        return validated_services
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al obtener servicios: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener servicios: {str(e)}"
        )

@router.post("/", response_model=Servicio, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionDependency("puede_editar_productos"))]
)
async def create_service(
    business_id: str,
    service_in: ServicioCreate,
    request: Request,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep)
) -> Any:
    """
    Create a new service for a specific business.
    """
    supabase = scoped.client
    context = scoped.context

    settings = context.branch_settings or {}
    servicios_modo = settings.get("servicios_modo", "centralizado")

    try:
        if service_in.categoria_id:
            category_response = supabase.table("categorias").select("id").eq("id", service_in.categoria_id).eq("negocio_id", business_id).execute()
            if not category_response.data:
                raise HTTPException(status_code=404, detail="Categoría no encontrada.")

        service_data = service_in.model_dump()
        service_data["negocio_id"] = business_id
        
        # We ALWAYS insert into "servicios" first to create the base record
        response = supabase.table("servicios").insert(service_data).execute()

        if not response.data:
             raise HTTPException(status_code=400, detail="Error al crear el servicio base.")

        created_service = response.data[0]

        # If por_sucursal, we also insert into servicio_sucursal
        if servicios_modo == "por_sucursal" and context.branch_id:
            branch_data = {
                "negocio_id": business_id,
                "sucursal_id": context.branch_id,
                "servicio_id": created_service["id"],
                "precio": created_service.get("precio"),
                "estado": "activo" if created_service.get("activo", True) else "inactivo"
            }
            branch_response = supabase.table("servicio_sucursal").insert(branch_data).execute()
            if not branch_response.data:
                # Rollback or log? We just log for now
                logger.error(f"Failed to create branch record for service {created_service['id']}")
            
        return Servicio(**created_service)

    except HTTPException:
         raise
    except Exception as e:
        logger.error(f"Error al crear servicio: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear servicio: {str(e)}"
        )

@router.get("/{service_id}", response_model=Servicio,
    dependencies=[Depends(PermissionDependency("puede_ver_productos"))]
)
async def read_service(
    business_id: str,
    service_id: str,
    request: Request,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep)
) -> Any:
    """
    Get a specific service by ID for a business (requires puede_ver_productos).
    """
    supabase = scoped.client
    context = scoped.context

    settings = context.branch_settings or {}
    servicios_modo = settings.get("servicios_modo", "centralizado")
    table_name = "servicio_sucursal" if servicios_modo == "por_sucursal" else "servicios"

    try:
        query = supabase.table(table_name).select("*").eq("id", service_id).eq("negocio_id", business_id)
        if servicios_modo == "por_sucursal" and context.branch_id:
            query = query.eq("sucursal_id", context.branch_id)
            
        response = query.single().execute()

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
    dependencies=[Depends(PermissionDependency("puede_editar_productos"))]
)
async def update_service(
    business_id: str,
    service_id: str,
    service_update: ServicioUpdate,
    request: Request,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep)
) -> Any:
    """
    Update a service by ID for a business.
    """
    supabase = scoped.client
    context = scoped.context

    settings = context.branch_settings or {}
    servicios_modo = settings.get("servicios_modo", "centralizado")

    try:
        update_data = service_update.model_dump(exclude_unset=True)
        
        if "categoria_id" in update_data and update_data["categoria_id"] is not None:
             category_response = supabase.table("categorias").select("id").eq("id", update_data["categoria_id"]).eq("negocio_id", business_id).execute()
             if not category_response.data:
                  raise HTTPException(status_code=404, detail="Nueva categoría no encontrada.")

        if servicios_modo == "por_sucursal" and context.branch_id:
            # We split the update: basic info goes to "servicios", branch info goes to "servicio_sucursal"
            branch_update = {}
            if "precio" in update_data:
                branch_update["precio"] = update_data.pop("precio")
            if "activo" in update_data:
                branch_update["estado"] = "activo" if update_data.pop("activo") else "inactivo"
                
            if branch_update:
                branch_resp = supabase.table("servicio_sucursal").update(branch_update).eq("servicio_id", service_id).eq("sucursal_id", context.branch_id).execute()
                if not branch_resp.data:
                    # If it doesn't exist, we might need to upsert it
                    branch_update["negocio_id"] = business_id
                    branch_update["sucursal_id"] = context.branch_id
                    branch_update["servicio_id"] = service_id
                    supabase.table("servicio_sucursal").upsert(branch_update, on_conflict="servicio_id,sucursal_id").execute()
            
            # If there's still basic info to update
            if update_data:
                supabase.table("servicios").update(update_data).eq("id", service_id).eq("negocio_id", business_id).execute()
                
            # Fetch updated service
            updated_query = supabase.table("servicios").select("*, servicio_sucursal!inner(precio, estado, sucursal_id)").eq("id", service_id).eq("negocio_id", business_id).eq("servicio_sucursal.sucursal_id", context.branch_id)
            updated_service_response = updated_query.single().execute()
            
            item = updated_service_response.data
            if item and "servicio_sucursal" in item:
                branch_info = item.pop("servicio_sucursal")
                if isinstance(branch_info, list) and len(branch_info) > 0:
                    branch_info = branch_info[0]
                if isinstance(branch_info, dict):
                    if "precio" in branch_info:
                        item["precio"] = branch_info["precio"]
                    if "estado" in branch_info:
                        item["activo"] = (branch_info["estado"] == "activo")
            return Servicio(**item)
        else:
            # Centralizado: update the base table
            response = supabase.table("servicios").update(update_data).eq("id", service_id).eq("negocio_id", business_id).execute()
            if not response.data:
                 raise HTTPException(status_code=404, detail="Servicio no encontrado.")
            return Servicio(**response.data[0])

    except HTTPException:
         raise
    except Exception as e:
        logger.error(f"Error updating service: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al actualizar servicio: {str(e)}")

@router.delete("/{service_id}",
    dependencies=[Depends(PermissionDependency("puede_editar_productos"))]
)
async def delete_service(
    business_id: str,
    service_id: str,
    request: Request,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep)
):
    """
    Delete a service by ID for a business.
    """
    supabase = scoped.client
    context = scoped.context

    settings = context.branch_settings or {}
    servicios_modo = settings.get("servicios_modo", "centralizado")

    try:
        if servicios_modo == "por_sucursal" and context.branch_id:
            # Delete ONLY from servicio_sucursal
            response = supabase.table("servicio_sucursal").delete().eq("servicio_id", service_id).eq("sucursal_id", context.branch_id).execute()
        else:
            # Centralizado: Delete from base table (cascades to all branches)
            response = supabase.table("servicios").delete().eq("id", service_id).eq("negocio_id", business_id).execute()

        if not response.data:
            raise HTTPException(status_code=400, detail="Error al eliminar el servicio (posiblemente referenciado o inexistente).")

        return {"message": "Servicio eliminado exitosamente"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting service: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al eliminar servicio: {str(e)}") 