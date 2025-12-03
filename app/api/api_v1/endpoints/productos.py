from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Query
from pydantic import BaseModel, ValidationError
from app.types.auth import User
from app.api.deps import get_current_user_from_request as get_current_user
from app.db.supabase_client import get_supabase_anon_client
from app.db.scoped_client import get_scoped_supabase_user_client
from app.schemas.producto import ProductoCreate, ProductoUpdate, Producto
from app.dependencies import PermissionDependency
from app.core.permissions import check_subscription_access
import logging
import datetime

router = APIRouter()

# Configure logging
logger = logging.getLogger(__name__)

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
    token = request.headers.get("Authorization", "")
    supabase = (
        get_scoped_supabase_user_client(token, business_id)
        if token
        else get_supabase_anon_client()
    )
    
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
        
        # Validate and serialize each product individually to catch validation errors
        validated_products = []
        for item in products_data:
            try:
                # Ensure required fields are present and handle None values
                if not item.get('id'):
                    logger.warning(f"Skipping product without ID: {item}")
                    continue
                
                # Handle datetime fields properly
                if item.get('creado_en') and isinstance(item['creado_en'], str):
                    # If it's a string, try to parse it
                    try:
                        item['creado_en'] = datetime.datetime.fromisoformat(item['creado_en'].replace('Z', '+00:00'))
                    except ValueError:
                        logger.warning(f"Invalid creado_en format for product {item.get('id')}: {item.get('creado_en')}")
                        # Set a default value
                        item['creado_en'] = datetime.datetime.now()
                
                if item.get('actualizado_en') and isinstance(item['actualizado_en'], str):
                    try:
                        item['actualizado_en'] = datetime.datetime.fromisoformat(item['actualizado_en'].replace('Z', '+00:00'))
                    except ValueError:
                        logger.warning(f"Invalid actualizado_en format for product {item.get('id')}: {item.get('actualizado_en')}")
                        # Set a default value
                        item['actualizado_en'] = datetime.datetime.now()
                
                # Ensure required fields have default values
                if item.get('activo') is None:
                    item['activo'] = True
                
                validated_product = Producto(**item)
                validated_products.append(validated_product)
                
            except ValidationError as ve:
                logger.error(f"Validation error for product {item.get('id', 'unknown')}: {ve}")
                # Skip invalid products instead of failing the entire request
                continue
            except Exception as e:
                logger.error(f"Error processing product {item.get('id', 'unknown')}: {e}")
                continue
        
        return validated_products
        
    except HTTPException:
        # Re-raise HTTP exceptions as they are expected
        raise
    except Exception as e:
        logger.error(f"Error al obtener productos: {str(e)}")
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
    subscription_check: bool = Depends(check_subscription_access),
) -> Any:
    """
    Create a new product for a specific business, optionally within a category (requires puede_editar_productos).
    """
    token = request.headers.get("Authorization", "")
    supabase = (
        get_scoped_supabase_user_client(token, business_id)
        if token
        else get_supabase_anon_client()
    )

    try:
        # Verify that the category exists and belongs to the business (only if categoria_id is provided)
        if product_in.categoria_id:
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
            detail=f"Error al crear producto: {str(e)}"
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
    token = request.headers.get("Authorization", "")
    supabase = (
        get_scoped_supabase_user_client(token, business_id)
        if token
        else get_supabase_anon_client()
    )

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
    subscription_check: bool = Depends(check_subscription_access),
) -> Any:
    """
    Update a product by ID for a business (requires puede_editar_productos).
    """
    token = request.headers.get("Authorization", "")
    supabase = (
        get_scoped_supabase_user_client(token, business_id)
        if token
        else get_supabase_anon_client()
    )

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
    subscription_check: bool = Depends(check_subscription_access),
):
    """
    Delete a product by ID for a business (requires puede_editar_productos).
    """
    token = request.headers.get("Authorization", "")
    supabase = (
        get_scoped_supabase_user_client(token, business_id)
        if token
        else get_supabase_anon_client()
    )

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

# --- Catalog Upload & Bulk Import Endpoints ---

from fastapi import UploadFile, File
from app.schemas.producto import ProductoImportado, ImportacionMasiva
from app.services.pdf_parser import parse_pdf_catalog

@router.post("/upload-catalog", response_model=List[ProductoImportado],
    dependencies=[Depends(PermissionDependency("puede_editar_productos"))]
)
async def upload_catalog(
    business_id: str,
    file: UploadFile = File(...),
    request: Request = None,
    subscription_check: bool = Depends(check_subscription_access),
) -> Any:
    """
    Upload a PDF catalog and return parsed product data.
    
    This endpoint:
    1. Receives a PDF file.
    2. Parses it using the PDF parser service.
    3. Returns a list of potential products found in the PDF.
    
    The user is expected to review this data on the frontend before confirming the import.
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF.")
    
    try:
        contents = await file.read()
        products = parse_pdf_catalog(contents)
        
        # Convert to schema
        result = []
        for p in products:
            result.append(ProductoImportado(
                codigo=p['code'],
                descripcion=p['description'],
                precio_detectado=p['price_value'],
                precio_raw=p['raw_price'],
                pagina=p['page']
            ))
            
        return result
        
    except Exception as e:
        logger.error(f"Error processing catalog upload: {e}")
        raise HTTPException(status_code=500, detail=f"Error al procesar el catálogo: {str(e)}")

@router.post("/bulk-upsert", status_code=status.HTTP_200_OK,
    dependencies=[Depends(PermissionDependency("puede_editar_productos"))]
)
async def bulk_upsert_products(
    business_id: str,
    import_data: ImportacionMasiva,
    request: Request,
    subscription_check: bool = Depends(check_subscription_access),
) -> Any:
    """
    Bulk upsert products from confirmed import data.
    
    This endpoint:
    1. Receives a list of confirmed products and a price type (cost or sale).
    2. Iterates through the products.
    3. Checks if a product with the same code exists for this business.
    4. If exists: Updates price (cost or sale) and stock (adds to existing).
    5. If new: Creates the product.
    """
    token = request.headers.get("Authorization", "")
    supabase = (
        get_scoped_supabase_user_client(token, business_id)
        if token
        else get_supabase_anon_client()
    )
    
    processed_count = 0
    errors = []
    
    for item in import_data.productos:
        try:
            # Check if product exists by code
            existing = None
            if item.codigo:
                resp = supabase.table("productos").select("*").eq("negocio_id", business_id).eq("codigo", item.codigo).execute()
                if resp.data:
                    existing = resp.data[0]
            
            product_data = {}
            
            # Determine price fields based on tipo_precio
            if import_data.tipo_precio == 'costo':
                product_data['precio_compra'] = item.precio
                # If new product, we must set a sale price too. 
                # If we don't have one, maybe default to cost * markup or just cost.
                # For now, if new, let's set sale price = cost (user can update later)
                if not existing:
                    product_data['precio_venta'] = item.precio 
            else: # venta
                product_data['precio_venta'] = item.precio
                
            if existing:
                # Update logic
                # We only update the price specified.
                # We might also want to update description if it changed? 
                # Let's assume description from PDF might be better or worse. 
                # For now, let's ONLY update price and stock if provided.
                
                # Update stock? The prompt says "cargue o actualice de una manera masiva".
                # Usually catalogs don't have stock, but if they do (or if we treat this as stock entry),
                # we should add to stock.
                # The prompt says "complementar la información faltante".
                
                # Let's update description if existing is empty
                if not existing.get('descripcion') and item.descripcion:
                    product_data['descripcion'] = item.descripcion
                    
                # Update stock - add to existing
                # Wait, the PDF is a price list, usually doesn't have stock quantity.
                # But our schema has 'stock' default 0.
                # If the user input stock in the review table, we should add it.
                if item.stock > 0:
                    product_data['stock_actual'] = existing['stock_actual'] + item.stock
                
                supabase.table("productos").update(product_data).eq("id", existing['id']).execute()
                
            else:
                # Create logic
                product_data['negocio_id'] = business_id
                product_data['nombre'] = item.nombre # Use description as name if name not provided?
                # In our schema 'nombre' is required. The PDF parser extracts 'description'.
                # We should map description to nombre for new products if nombre is missing?
                # The frontend should ensure 'nombre' is populated (maybe from description).
                
                product_data['descripcion'] = item.descripcion
                product_data['codigo'] = item.codigo
                product_data['stock_actual'] = item.stock
                product_data['activo'] = True
                
                # Ensure required fields
                if 'precio_venta' not in product_data:
                    product_data['precio_venta'] = 0 # Should not happen due to logic above
                    
                supabase.table("productos").insert(product_data).execute()
                
            processed_count += 1
            
        except Exception as e:
            logger.error(f"Error upserting product {item.codigo}: {e}")
            errors.append(f"Error con producto {item.codigo}: {str(e)}")
            
    return {
        "message": f"Procesados {processed_count} productos.",
        "errors": errors
    } 
