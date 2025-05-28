from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from app.types.auth import User
from app.api.deps import get_current_user
from app.db.supabase_client import get_supabase_client
from app.schemas.producto import ProductoCreate, ProductoUpdate, Producto

router = APIRouter()

@router.get("/", response_model=List[Producto])
async def read_productos(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Retrieve products.
    """
    try:
        supabase = get_supabase_client()
        response = supabase.table("productos").select("*").range(skip, skip + limit - 1).execute()
        return response.data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener productos: {str(e)}"
        )

@router.post("/", response_model=Producto)
async def create_producto(
    *,
    producto_in: ProductoCreate,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Create new product.
    """
    try:
        supabase = get_supabase_client()
        
        # Verificar que la categoría existe
        categoria = supabase.table("categorias").select("id").eq("id", producto_in.id_categoria).execute()
        if not categoria.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoría no encontrada"
            )
        
        # Crear el producto
        producto_data = producto_in.model_dump()
        response = supabase.table("productos").insert(producto_data).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error al crear el producto"
            )
            
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear producto: {str(e)}"
        )

@router.get("/{producto_id}", response_model=Producto)
async def read_producto(
    producto_id: str,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get product by ID.
    """
    try:
        supabase = get_supabase_client()
        response = supabase.table("productos").select("*").eq("id", producto_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Producto no encontrado"
            )
            
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener producto: {str(e)}"
        )

@router.put("/{producto_id}", response_model=Producto)
async def update_producto(
    *,
    producto_id: str,
    producto_in: ProductoUpdate,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Update a product.
    """
    try:
        supabase = get_supabase_client()
        
        # Verificar que el producto existe
        producto = supabase.table("productos").select("id").eq("id", producto_id).execute()
        if not producto.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Producto no encontrado"
            )
        
        # Actualizar el producto
        update_data = producto_in.model_dump(exclude_unset=True)
        response = supabase.table("productos").update(update_data).eq("id", producto_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error al actualizar el producto"
            )
            
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar producto: {str(e)}"
        )

@router.delete("/{producto_id}")
async def delete_producto(
    producto_id: str,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Delete a product.
    """
    try:
        supabase = get_supabase_client()
        
        # Verificar que el producto existe
        producto = supabase.table("productos").select("id").eq("id", producto_id).execute()
        if not producto.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Producto no encontrado"
            )
        
        # Eliminar el producto (soft delete)
        response = supabase.table("productos").update({"activo": False}).eq("id", producto_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error al eliminar el producto"
            )
            
        return {"detail": "Producto eliminado correctamente"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar producto: {str(e)}"
        ) 