from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from app.types.auth import User
from app.api.deps import get_current_user
from app.db.supabase_client import get_supabase_client
from app.schemas.categoria import CategoriaCreate, CategoriaUpdate, Categoria

router = APIRouter()

@router.get("/", response_model=List[Categoria])
async def read_categorias(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Retrieve categories.
    """
    try:
        supabase = get_supabase_client()
        response = supabase.table("categorias").select("*").range(skip, skip + limit - 1).execute()
        return response.data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener categorías: {str(e)}"
        )

@router.post("/", response_model=Categoria)
async def create_categoria(
    *,
    categoria_in: CategoriaCreate,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Create new category.
    """
    try:
        supabase = get_supabase_client()
        categoria_data = categoria_in.model_dump()
        response = supabase.table("categorias").insert(categoria_data).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error al crear la categoría"
            )
            
        return response.data[0]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear categoría: {str(e)}"
        )

@router.get("/{categoria_id}", response_model=Categoria)
async def read_categoria(
    categoria_id: str,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get category by ID.
    """
    try:
        supabase = get_supabase_client()
        response = supabase.table("categorias").select("*").eq("id", categoria_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoría no encontrada"
            )
            
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener categoría: {str(e)}"
        )

@router.put("/{categoria_id}", response_model=Categoria)
async def update_categoria(
    *,
    categoria_id: str,
    categoria_in: CategoriaUpdate,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Update a category.
    """
    try:
        supabase = get_supabase_client()
        
        # Verificar que la categoría existe
        categoria = supabase.table("categorias").select("id").eq("id", categoria_id).execute()
        if not categoria.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoría no encontrada"
            )
        
        # Actualizar la categoría
        update_data = categoria_in.model_dump(exclude_unset=True)
        response = supabase.table("categorias").update(update_data).eq("id", categoria_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error al actualizar la categoría"
            )
            
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar categoría: {str(e)}"
        )

@router.delete("/{categoria_id}")
async def delete_categoria(
    categoria_id: str,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Delete a category.
    """
    try:
        supabase = get_supabase_client()
        
        # Verificar que la categoría existe
        categoria = supabase.table("categorias").select("id").eq("id", categoria_id).execute()
        if not categoria.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoría no encontrada"
            )
        
        # Verificar si hay productos asociados
        productos = supabase.table("productos").select("id").eq("categoria_id", categoria_id).execute()
        if productos.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se puede eliminar la categoría porque tiene productos asociados"
            )
        
        # Eliminar la categoría
        response = supabase.table("categorias").delete().eq("id", categoria_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error al eliminar la categoría"
            )
            
        return {"detail": "Categoría eliminada correctamente"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar categoría: {str(e)}"
        ) 