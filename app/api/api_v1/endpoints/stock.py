from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status

from app import types
from app.api.context import BusinessScopedClientDep, ScopedClientContext

router = APIRouter()


@router.get("/", response_model=List[types.Producto])
async def get_productos(
    business_id: str,
    skip: int = 0,
    limit: int = 100,
    only_active: bool = True,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """
    Obtener listado de productos en stock para un negocio.
    """
    supabase = scoped.client
    query = supabase.table("productos").select("*").eq("negocio_id", business_id)

    if only_active:
        query = query.eq("activo", True)

    response = query.range(skip, skip + limit - 1).execute()
    return response.data


@router.post("/", response_model=types.Producto)
async def create_producto(
    *,
    business_id: str,
    producto_in: types.ProductoCreate,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """
    Crear un nuevo producto para un negocio.
    """
    supabase = scoped.client

    if producto_in.codigo:
        existing = (
            supabase.table("productos")
            .select("id")
            .eq("negocio_id", business_id)
            .eq("codigo", producto_in.codigo)
            .limit(1)
            .execute()
        )
        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe un producto con este código en el negocio.",
            )

    payload = producto_in.model_dump()
    payload["negocio_id"] = business_id

    response = supabase.table("productos").insert(payload).execute()
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear el producto",
        )

    return response.data[0]


@router.get("/{producto_id}", response_model=types.Producto)
async def get_producto(
    *,
    business_id: str,
    producto_id: int,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """
    Obtener un producto por ID dentro de un negocio.
    """
    supabase = scoped.client
    response = (
        supabase.table("productos")
        .select("*")
        .eq("negocio_id", business_id)
        .eq("id", producto_id)
        .maybe_single()
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado en este negocio",
        )

    return response.data


@router.put("/{producto_id}", response_model=types.Producto)
async def update_producto(
    *,
    business_id: str,
    producto_id: int,
    producto_in: types.ProductoUpdate,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """
    Actualizar un producto de un negocio.
    """
    supabase = scoped.client
    exists = (
        supabase.table("productos")
        .select("id")
        .eq("negocio_id", business_id)
        .eq("id", producto_id)
        .limit(1)
        .execute()
    )
    if not exists.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado en este negocio",
        )

    update_data = producto_in.model_dump(exclude_unset=True)
    response = (
        supabase.table("productos")
        .update(update_data)
        .eq("negocio_id", business_id)
        .eq("id", producto_id)
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar el producto",
        )

    return response.data[0]


@router.delete("/{producto_id}", response_model=types.Producto)
async def delete_producto(
    *,
    business_id: str,
    producto_id: int,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """
    Desactivar un producto dentro de un negocio.
    """
    supabase = scoped.client
    exists = (
        supabase.table("productos")
        .select("id")
        .eq("negocio_id", business_id)
        .eq("id", producto_id)
        .limit(1)
        .execute()
    )
    if not exists.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado en este negocio",
        )

    response = (
        supabase.table("productos")
        .update({"activo": False})
        .eq("negocio_id", business_id)
        .eq("id", producto_id)
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al desactivar el producto",
        )

    return response.data[0]


@router.post("/importar")
async def importar_productos(
    *,
    business_id: str,
    file: UploadFile = File(...),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """
    Importar productos desde un archivo (placeholder).
    """
    _ = scoped.client  # placeholder for futura integración
    return {
        "message": f"Archivo {file.filename} importado correctamente",
        "negocio_id": business_id,
    }
