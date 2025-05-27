from typing import Any, List, Dict

from fastapi import APIRouter, HTTPException, UploadFile, File, status, Depends

# Import dependencies and schemas
from app.api import deps
from app.schemas.usuario import Usuario as CurrentUserSchema # To type hint current_user
from app.models.supabase_models import Producto as ProductoModel
from app import schemas
from app.db.supabase_client import get_supabase_client

router = APIRouter()


@router.get("/", response_model=List[schemas.Producto])
async def get_productos(
    skip: int = 0,
    limit: int = 100,
    only_active: bool = True,
    current_user: CurrentUserSchema = Depends(deps.get_current_user) # Protected
) -> Any:
    """
    Obtener listado de productos en stock. Requiere autenticación.
    """
    supabase = get_supabase_client()
    query = supabase.table("productos").select("*")
    
    if only_active:
        query = query.eq("activo", True)
    
    response = query.range(skip, skip + limit - 1).execute()
    return response.data


@router.post("/", response_model=schemas.Producto)
async def create_producto(
    *,
    producto_in: schemas.ProductoCreate,
    current_user: CurrentUserSchema = Depends(deps.get_current_user) # Protected
) -> Any:
    """
    Crear un nuevo producto. Requiere autenticación.
    """
    supabase = get_supabase_client()
    
    # Check if product code already exists
    if producto_in.codigo:
        response = supabase.table("productos").select("*").eq("codigo", producto_in.codigo).execute()
        if response.data and len(response.data) > 0:
            raise HTTPException(
                status_code=400,
                detail="Ya existe un producto con este código.",
            )
    
    # Create product
    producto_data = producto_in.model_dump()
    response = supabase.table("productos").insert(producto_data).execute()
    
    if not response.data or len(response.data) == 0:
        raise HTTPException(
            status_code=500,
            detail="Error al crear el producto",
        )
    
    return response.data[0]


@router.get("/{producto_id}", response_model=schemas.Producto)
async def get_producto(
    *,
    producto_id: int,
    current_user: CurrentUserSchema = Depends(deps.get_current_user) # Protected
) -> Any:
    """
    Obtener un producto por ID. Requiere autenticación.
    """
    supabase = get_supabase_client()
    response = supabase.table("productos").select("*").eq("id", producto_id).execute()
    
    if not response.data or len(response.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado",
        )
    
    return response.data[0]


@router.put("/{producto_id}", response_model=schemas.Producto)
async def update_producto(
    *,
    producto_id: int,
    producto_in: schemas.ProductoUpdate,
    current_user: CurrentUserSchema = Depends(deps.get_current_user) # Protected
) -> Any:
    """
    Actualizar un producto. Requiere autenticación.
    """
    supabase = get_supabase_client()
    
    # Check if product exists
    response = supabase.table("productos").select("*").eq("id", producto_id).execute()
    if not response.data or len(response.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado",
        )
    
    # Update product
    producto_data = producto_in.model_dump(exclude_unset=True)
    response = supabase.table("productos").update(producto_data).eq("id", producto_id).execute()
    
    if not response.data or len(response.data) == 0:
        raise HTTPException(
            status_code=500,
            detail="Error al actualizar el producto",
        )
    
    return response.data[0]


@router.delete("/{producto_id}", response_model=schemas.Producto)
async def delete_producto(
    *,
    producto_id: int,
    current_user: CurrentUserSchema = Depends(deps.get_current_user) # Protected
) -> Any:
    """
    Eliminar un producto. Requiere autenticación.
    """
    supabase = get_supabase_client()
    
    # Check if product exists
    response = supabase.table("productos").select("*").eq("id", producto_id).execute()
    if not response.data or len(response.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado",
        )
    
    # Delete product (or mark as inactive)
    # Option 1: Physical deletion
    # response = supabase.table("productos").delete().eq("id", producto_id).execute()
    
    # Option 2: Logical deletion (recommended)
    response = supabase.table("productos").update({"activo": False}).eq("id", producto_id).execute()
    
    return response.data[0]


@router.post("/importar")
async def importar_productos(
    file: UploadFile = File(...),
    current_user: CurrentUserSchema = Depends(deps.get_current_user) # Protected
) -> Any:
    """
    Importar productos desde un archivo Excel. Requiere autenticación.
    """
    # Aquí iría la lógica para importar productos desde Excel
    # Por ahora devolvemos una respuesta básica
    return {"message": f"Archivo {file.filename} importado correctamente"} 