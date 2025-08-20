from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query, Response
from app.db.supabase_client import get_supabase_user_client
from app.schemas.proveedor import Proveedor, ProveedorCreate, ProveedorUpdate
from app.dependencies import PermissionDependency

router = APIRouter()


@router.get(
    "/",
    response_model=List[Proveedor],
    dependencies=[Depends(PermissionDependency("stock", "ver"))]
)
@router.get(
    "",
    response_model=List[Proveedor],
    dependencies=[Depends(PermissionDependency("stock", "ver"))]
)
async def read_proveedores(
    business_id: str,
    request: Request,
    q: Optional[str] = Query(None, description="Buscar por nombre (ilike)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Any:
    """
    Lista proveedores del negocio con búsqueda simple por nombre y paginación.
    """
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token requerido")

    client = get_supabase_user_client(authorization)

    try:
        query = client.table("proveedores").select("*").eq("negocio_id", business_id)
        if q:
            query = query.ilike("nombre", f"%{q}%")
        if offset or limit:
            query = query.range(offset, offset + limit - 1)
        resp = query.execute()
        return resp.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener proveedores: {str(e)}")


@router.get(
    "/{proveedor_id}",
    response_model=Proveedor,
    dependencies=[Depends(PermissionDependency("stock", "ver"))]
)
async def read_proveedor(
    business_id: str,
    proveedor_id: str,
    request: Request,
) -> Any:
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token requerido")

    client = get_supabase_user_client(authorization)

    try:
        resp = (
            client
            .table("proveedores")
            .select("*")
            .eq("id", proveedor_id)
            .eq("negocio_id", business_id)
            .single()
            .execute()
        )
        if not resp.data:
            raise HTTPException(status_code=404, detail="Proveedor no encontrado")
        return resp.data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener proveedor: {str(e)}")


@router.post(
    "/",
    response_model=Proveedor,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionDependency("stock", "editar"))]
)
@router.post(
    "",
    response_model=Proveedor,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionDependency("stock", "editar"))]
)
async def create_proveedor(
    business_id: str,
    proveedor_in: ProveedorCreate,
    request: Request,
) -> Any:
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token requerido")

    client = get_supabase_user_client(authorization)

    try:
        data = proveedor_in.model_dump()
        data["negocio_id"] = business_id
        resp = client.table("proveedores").insert(data).execute()
        if not resp.data:
            raise HTTPException(status_code=400, detail="No se pudo crear el proveedor")
        return resp.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al crear proveedor: {str(e)}")


@router.put(
    "/{proveedor_id}",
    response_model=Proveedor,
    dependencies=[Depends(PermissionDependency("stock", "editar"))]
)
async def update_proveedor(
    business_id: str,
    proveedor_id: str,
    proveedor_update: ProveedorUpdate,
    request: Request,
) -> Any:
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token requerido")

    client = get_supabase_user_client(authorization)

    try:
        update_data = proveedor_update.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No hay datos para actualizar")
        resp = (
            client
            .table("proveedores")
            .update(update_data)
            .eq("id", proveedor_id)
            .eq("negocio_id", business_id)
            .execute()
        )
        if not resp.data:
            raise HTTPException(status_code=404, detail="Proveedor no encontrado o sin cambios")
        return resp.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al actualizar proveedor: {str(e)}")


@router.delete(
    "/{proveedor_id}",
    dependencies=[Depends(PermissionDependency("stock", "editar"))]
)
async def delete_proveedor(
    business_id: str,
    proveedor_id: str,
    request: Request,
) -> Any:
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token requerido")

    client = get_supabase_user_client(authorization)

    try:
        # Optional: deny delete if has compras asociadas
        compras_resp = client.table("compras").select("id").eq("proveedor_id", proveedor_id).eq("negocio_id", business_id).limit(1).execute()
        if compras_resp.data:
            raise HTTPException(status_code=400, detail="No se puede eliminar: proveedor con compras asociadas")

        resp = client.table("proveedores").delete().eq("id", proveedor_id).eq("negocio_id", business_id).execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Proveedor no encontrado")
        return {"message": "Proveedor eliminado correctamente"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar proveedor: {str(e)}")
