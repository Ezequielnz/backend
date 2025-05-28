from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Query
from pydantic import BaseModel
from app.types.auth import User
from app.api.deps import get_current_user
from app.db.supabase_client import get_supabase_client
from app.schemas.producto import ProductoCreate, ProductoUpdate, Producto
from app.dependencies import PermissionDependency

router = APIRouter()

class ProductBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    precio: float
    stock: int
    # Add other potential product fields here

class ProductCreate(ProductBase):
    categoria_id: str # Include category_id in create payload

class ProductUpdate(BaseModel): # Use a separate model for update to make fields optional
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    precio: Optional[float] = None
    stock: Optional[int] = None
    categoria_id: Optional[str] = None # Allow changing category

class Product(ProductBase):
    id: str
    negocio_id: str
    categoria_id: str

    class Config:
        from_attributes = True # or orm_mode = True for older Pydantic versions

# Endpoint to list products for a specific business (optional filter by category)
@router.get("/", response_model=List[Producto],
    dependencies=[Depends(PermissionDependency("puede_ver_productos"))]
)
async def read_products(
    business_id: str,
    request: Request,
    category_id: Optional[str] = Query(None, description="Optional category ID to filter products"),
) -> Any:
    """
    Retrieve products for a specific business, optionally filtered by category (requires puede_ver_productos).
    """
    supabase = get_supabase_client()
    
    try:
        query = supabase.table("productos").select("*").eq("negocio_id", business_id)
        
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
        products_data = response.data if response.data is not None else []
        
        return [Producto(**item) for item in products_data]
        
    except Exception as e:
        print(f"Error al obtener productos: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener productos: {str(e)}"
        )

# Endpoint to create a new product within a specific category and business
@router.post("/", response_model=Producto, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionDependency("puede_editar_productos"))]
)
async def create_product(
    business_id: str,
    product_in: ProductoCreate,
    request: Request,
) -> Any:
    """
    Create a new product for a specific category within a business (requires puede_editar_productos).
    """
    supabase = get_supabase_client()

    try:
        # Verify that the category exists and belongs to the business
        category_response = supabase.table("categorias").select("id").eq("id", product_in.categoria_id).eq("negocio_id", business_id).execute()
        if not category_response.data:
             raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoría especificada no encontrada o no pertenece a este negocio.",
            )

        product_data = product_in.model_dump()
        product_data["negocio_id"] = business_id

        response = supabase.table("productos").insert(product_data).execute()

        if not response.data:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error al crear el producto.",
            )

        return Producto(**response.data[0])

    except HTTPException:
         raise
    except Exception as e:
        print(f"Error al crear producto: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear producto: {str(e)}",
        )

@router.get("/{product_id}", response_model=Producto,
    dependencies=[Depends(PermissionDependency("puede_ver_productos"))]
)
async def read_product(
    business_id: str,
    product_id: str,
    request: Request,
) -> Any:
    """
    Get a specific product by ID for a business (requires puede_ver_productos).
    """
    supabase = get_supabase_client()

    try:
        response = supabase.table("productos").select("*").eq("id", product_id).eq("negocio_id", business_id).single().execute()

        return Producto(**response.data)

    except Exception as e:
        if "PostgrestSingleError" in str(e):
             raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Producto no encontrado o no pertenece a este negocio.",
            )
        print(f"Error fetching product: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener producto: {str(e)}",
        )

@router.put("/{product_id}", response_model=Producto,
    dependencies=[Depends(PermissionDependency("puede_editar_productos"))]
)
async def update_product(
    business_id: str,
    product_id: str,
    product_update: ProductoUpdate,
    request: Request,
) -> Any:
    """
    Update a product by ID for a business (requires puede_editar_productos).
    """
    supabase = get_supabase_client()

    try:
        update_data = product_update.model_dump(exclude_unset=True)
        
        # If category_id is being updated, verify it exists and belongs to the business
        if "categoria_id" in update_data and update_data["categoria_id"] is not None:
             category_response = supabase.table("categorias").select("id").eq("id", update_data["categoria_id"]).eq("negocio_id", business_id).execute()
             if not category_response.data:
                  raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Nueva categoría especificada no encontrada o no pertenece a este negocio.",
                 )

        # Update the product, ensuring it belongs to the correct business
        response = supabase.table("productos").update(update_data).eq("id", product_id).eq("negocio_id", business_id).execute()

        if not response.data:
             # Check if product exists but doesn't belong to business, or doesn't exist at all
             existing_product = supabase.table("productos").select("id").eq("id", product_id).execute()
             if existing_product.data:
                  raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Producto no pertenece a este negocio.",
                 )
             else:
                  raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Producto no encontrado.",
                 )
        
        # Fetch the updated product to return
        updated_product_response = supabase.table("productos").select("*").eq("id", product_id).single().execute()
        return Producto(**updated_product_response.data)

    except HTTPException:
         raise
    except Exception as e:
        print(f"Error updating product: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar producto: {str(e)}",
        )

@router.delete("/{product_id}",
    dependencies=[Depends(PermissionDependency("puede_editar_productos"))]
)
async def delete_product(
    business_id: str,
    product_id: str,
    request: Request,
):
    """
    Delete a product by ID for a business (requires puede_editar_productos).
    """
    supabase = get_supabase_client()

    try:
        # First, check if the product exists and belongs to the business
        existing_product_response = supabase.table("productos").select("id").eq("id", product_id).eq("negocio_id", business_id).execute()
        
        if not existing_product_response.data:
             raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Producto no encontrado o no pertenece a este negocio.",
            )

        # Delete the product
        supabase.table("productos").delete().eq("id", product_id).eq("negocio_id", business_id).execute()

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except HTTPException:
         raise
    except Exception as e:
        print(f"Error deleting product: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar producto: {str(e)}",
        ) 