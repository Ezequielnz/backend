from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from app.types.auth import User
from app.api.deps import get_current_user
from app.db.supabase_client import get_supabase_client
from app.schemas.categoria import CategoriaCreate, CategoriaUpdate, Categoria
from app.dependencies import verify_permission, PermissionDependency

router = APIRouter()

@router.get("/", response_model=List[Categoria],
    dependencies=[Depends(PermissionDependency("puede_ver_categorias"))]
)
async def read_categorias(
    business_id: str,
    request: Request,
) -> Any:
    """
    Retrieve categories for a specific business (requires puede_ver_categorias).
    """
    supabase = get_supabase_client()

    try:
        # Fetch categories filtered by business_id
        response = supabase.table("categorias").select("*").eq("negocio_id", business_id).execute()
        
        # Ensure data is a list, even if empty
        categories_data = response.data if response.data is not None else []

        # Pydantic will validate the list of category objects
        return [Categoria(**item) for item in categories_data]

    except Exception as e:
        print(f"Error fetching categories: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener categorías: {str(e)}"
        )

@router.post("/", response_model=Categoria, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionDependency("puede_editar_categorias"))]
)
async def create_categoria(
    business_id: str,
    categoria_in: CategoriaCreate,
    request: Request,
) -> Any:
    """
    Create new category for a specific business (requires puede_editar_categorias).
    """
    supabase = get_supabase_client()
    
    try:
        # Ensure the category is created for the correct business
        categoria_data = categoria_in.model_dump()
        categoria_data["negocio_id"] = business_id

        response = supabase.table("categorias").insert(categoria_data).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error al crear la categoría"
            )
            
        return Categoria(**response.data[0])
    except Exception as e:
        print(f"Error al crear categoría: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear categoría: {str(e)}"
        )

@router.get("/{categoria_id}", response_model=Categoria,
    dependencies=[Depends(PermissionDependency("puede_ver_categorias"))]
)
async def read_categoria(
    business_id: str,
    categoria_id: str,
    request: Request,
) -> Any:
    """
    Get a specific category by ID for a business (requires puede_ver_categorias).
    """
    supabase = get_supabase_client()

    try:
        # Fetch the category by ID and business_id
        response = supabase.table("categorias").select("*").eq("id", categoria_id).eq("negocio_id", business_id).single().execute()

        return Categoria(**response.data)

    except Exception as e:
        if "PostgrestSingleError" in str(e):
             raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoría no encontrada o no pertenece a este negocio.",
            )
        print(f"Error fetching category: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener categoría: {str(e)}",
        )

@router.put("/{categoria_id}", response_model=Categoria,
    dependencies=[Depends(PermissionDependency("puede_editar_categorias"))]
)
async def update_categoria(
    business_id: str,
    categoria_id: str,
    categoria_in: CategoriaUpdate,
    request: Request,
) -> Any:
    """
    Update a category by ID for a business (requires puede_editar_categorias).
    """
    supabase = get_supabase_client()

    try:
        # First, check if the category exists and belongs to the business
        existing_category_response = supabase.table("categorias").select("id").eq("id", categoria_id).eq("negocio_id", business_id).execute()
        
        if not existing_category_response.data:
             raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoría no encontrada o no pertenece a este negocio.",
            )

        # Update the category
        update_data = categoria_in.model_dump(exclude_unset=True)
        response = supabase.table("categorias").update(update_data).eq("id", categoria_id).execute()

        if not response.data:
             raise HTTPException(
                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail="Error al actualizar la categoría en Supabase.",
            )
        
        # Fetch the updated category to return
        updated_category_response = supabase.table("categorias").select("*").eq("id", categoria_id).single().execute()
        return Categoria(**updated_category_response.data)

    except HTTPException:
         raise
    except Exception as e:
        print(f"Error updating category: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar categoría: {str(e)}",
        )

@router.delete("/{categoria_id}",
    dependencies=[Depends(PermissionDependency("puede_editar_categorias"))]
)
async def delete_categoria(
    business_id: str,
    categoria_id: str,
    request: Request,
):
    """
    Delete a category by ID for a business (requires puede_editar_categorias).
    """
    supabase = get_supabase_client()

    try:
        # First, check if the category exists and belongs to the business
        existing_category_response = supabase.table("categorias").select("id").eq("id", categoria_id).eq("negocio_id", business_id).execute()
        
        if not existing_category_response.data:
             raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoría no encontrada o no pertenece a este negocio.",
            )

        # Check if there are products associated with this category within this business
        products_response = supabase.table("productos").select("id").eq("categoria_id", categoria_id).eq("negocio_id", business_id).execute()
        if products_response.data and len(products_response.data) > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se puede eliminar la categoría porque tiene productos asociados a este negocio."
            )
            
        # Delete the category
        supabase.table("categorias").delete().eq("id", categoria_id).eq("negocio_id", business_id).execute()

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except HTTPException:
         raise
    except Exception as e:
        print(f"Error deleting category: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar categoría: {str(e)}",
        ) 