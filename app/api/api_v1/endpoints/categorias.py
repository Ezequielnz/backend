from typing import List, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response
from supabase.client import Client

from app.db.supabase_client import get_supabase_client
from app.api import deps
from app.schemas.usuario import Usuario as CurrentUserSchema
from app.schemas.categoria import Categoria, CategoriaCreate, CategoriaUpdate

router = APIRouter()

@router.post("/", response_model=Categoria, status_code=status.HTTP_201_CREATED)
async def create_category(
    *,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
    category_in: CategoriaCreate
) -> Any:
    """
    Create a new category.
    """
    # Check if category name already exists (optional, but good practice)
    existing_category_response = await supabase.table("categorias").select("id").eq("nombre", category_in.nombre).execute()
    if existing_category_response.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A category with this name already exists.",
        )

    response = await supabase.table("categorias").insert(category_in.model_dump()).execute()
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create category.",
        )
    return response.data[0]

@router.get("/", response_model=List[Categoria])
async def list_categories(
    *,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
    skip: int = 0,
    limit: int = 100
) -> Any:
    """
    Retrieve a list of categories.
    """
    response = await supabase.table("categorias").select("*").range(skip, skip + limit - 1).execute()
    if response.data is None: # Check for None specifically if that's how Supabase client indicates error vs empty
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve categories."
        )
    return response.data

@router.get("/{categoria_id}", response_model=Categoria)
async def get_category(
    *,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
    categoria_id: int
) -> Any:
    """
    Get a specific category by its ID.
    """
    response = await supabase.table("categorias").select("*").eq("id", categoria_id).single().execute()
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category with ID {categoria_id} not found.",
        )
    return response.data

@router.put("/{categoria_id}", response_model=Categoria)
async def update_category(
    *,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
    categoria_id: int,
    category_in: CategoriaUpdate
) -> Any:
    """
    Update an existing category.
    """
    # First, check if the category exists
    existing_category = await supabase.table("categorias").select("id").eq("id", categoria_id).maybe_single().execute()
    if not existing_category.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category with ID {categoria_id} not found.",
        )

    # Check if the new name (if provided) conflicts with another existing category
    if category_in.nombre:
        conflict_response = await supabase.table("categorias").select("id").eq("nombre", category_in.nombre).neq("id", categoria_id).execute()
        if conflict_response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Another category with the name '{category_in.nombre}' already exists.",
            )
            
    update_data = category_in.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update provided.",
        )

    response = await supabase.table("categorias").update(update_data).eq("id", categoria_id).execute()
    if not response.data: # Should check if update actually happened or if data is empty due to error
        # Supabase update returns the updated records. If empty, it might mean not found or error.
        # The check above for existence should handle not found, so this implies another issue.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, # Or re-check not found if Supabase behaves differently
            detail=f"Could not update category with ID {categoria_id}.",
        )
    return response.data[0]

@router.delete("/{categoria_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    *,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
    categoria_id: int
) -> Response:
    """
    Delete a category.
    Deletion is disallowed if there are products linked to this category.
    """
    # Check if the category exists
    category_to_delete = await supabase.table("categorias").select("id").eq("id", categoria_id).maybe_single().execute()
    if not category_to_delete.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category with ID {categoria_id} not found.",
        )

    # Check for linked products
    linked_products_response = await supabase.table("productos").select("id", count="exact").eq("categoria_id", categoria_id).execute()
    if linked_products_response.count and linked_products_response.count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete category with ID {categoria_id} as it has {linked_products_response.count} associated products.",
        )

    await supabase.table("categorias").delete().eq("id", categoria_id).execute()
    # No need to check response.data for delete, as it doesn't return the deleted item by default
    # If the delete fails due to RLS or other reasons, Supabase client might raise an error.
    # If no error is raised, assume success.
    return Response(status_code=status.HTTP_204_NO_CONTENT)
