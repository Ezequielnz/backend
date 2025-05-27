from typing import List, Any, Optional, Dict

from fastapi import APIRouter, Depends, HTTPException, status, Response, UploadFile, File
from supabase.client import Client
import pandas as pd # Added for Excel import

from app.db.supabase_client import get_supabase_client
from app.api import deps
from app.schemas.usuario import Usuario as CurrentUserSchema
from app.schemas.producto import Producto, ProductoCreate, ProductoUpdate
from app.schemas.categoria import Categoria # For validation
from app.schemas.common import ImportSummary # Added for import response

router = APIRouter()

# Helper function to validate category_id
async def _validate_category_id(supabase: Client, categoria_id: int) -> None:
    if categoria_id is not None:
        category_response = await supabase.table("categorias").select("id").eq("id", categoria_id).maybe_single().execute()
        if not category_response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid categoria_id: Category with ID {categoria_id} does not exist.",
            )

@router.post("/", response_model=Producto, status_code=status.HTTP_201_CREATED)
async def create_product(
    *,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
    product_in: ProductoCreate
) -> Any:
    """
    Create a new product.
    `category_id` must be a valid ID from the `categorias` table.
    """
    if product_in.categoria_id is not None:
        await _validate_category_id(supabase, product_in.categoria_id)

    # Check if product code already exists (if provided)
    if product_in.codigo:
        existing_code_response = await supabase.table("productos").select("id").eq("codigo", product_in.codigo).execute()
        if existing_code_response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product with code '{product_in.codigo}' already exists.",
            )
            
    insert_data = product_in.model_dump()
    response = await supabase.table("productos").insert(insert_data).select("*, categoria:categorias(*)").single().execute()
    
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create product.",
        )
    return response.data

@router.get("/", response_model=List[Producto])
async def list_products(
    *,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
    skip: int = 0,
    limit: int = 100,
    category_id: Optional[int] = None,
    only_active: bool = True # Default to fetching only active products
) -> Any:
    """
    Retrieve a list of products, optionally filtered by category_id and active status.
    Includes nested category details.
    """
    query = supabase.table("productos").select("*, categoria:categorias(*)")
    
    if category_id is not None:
        query = query.eq("categoria_id", category_id)
    
    if only_active:
        query = query.eq("activo", True)
        
    response = await query.range(skip, skip + limit - 1).execute()
    
    if response.data is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve products."
        )
    return response.data

@router.get("/{producto_id}", response_model=Producto)
async def get_product(
    *,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
    producto_id: int
) -> Any:
    """
    Get a specific product by its ID, including nested category details.
    """
    response = await supabase.table("productos").select("*, categoria:categorias(*)").eq("id", producto_id).maybe_single().execute()
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {producto_id} not found.",
        )
    return response.data

@router.put("/{producto_id}", response_model=Producto)
async def update_product(
    *,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
    producto_id: int,
    product_in: ProductoUpdate
) -> Any:
    """
    Update an existing product.
    If `category_id` is provided, it must be a valid ID.
    """
    # Check if product exists
    existing_product_response = await supabase.table("productos").select("id, categoria_id").eq("id", producto_id).maybe_single().execute()
    if not existing_product_response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {producto_id} not found.",
        )

    # Validate categoria_id if it's being updated
    if product_in.categoria_id is not None and product_in.categoria_id != existing_product_response.data.get("categoria_id"):
        await _validate_category_id(supabase, product_in.categoria_id)

    # Check for code conflict if code is being updated
    if product_in.codigo:
        conflict_response = await supabase.table("productos").select("id").eq("codigo", product_in.codigo).neq("id", producto_id).execute()
        if conflict_response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Another product with the code '{product_in.codigo}' already exists.",
            )

    update_data = product_in.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update provided.",
        )
        
    response = await supabase.table("productos").update(update_data).eq("id", producto_id).select("*, categoria:categorias(*)").single().execute()
    
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not update product with ID {producto_id}.",
        )
    return response.data

@router.delete("/{producto_id}", response_model=Producto)
async def delete_product(
    *,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
    producto_id: int
) -> Any:
    """
    Delete a product (soft delete by setting 'activo' to False).
    Returns the updated product marked as inactive.
    """
    # Check if product exists and is active
    existing_product_response = await supabase.table("productos").select("id, activo").eq("id", producto_id).maybe_single().execute()
    if not existing_product_response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {producto_id} not found.",
        )
    
    if not existing_product_response.data.get("activo", True):
         # Product is already inactive, return current state or a specific message
        # For idempotency, we can return the current state as if it was just deactivated.
        # Fetch the full product data with category to return.
        full_product_response = await supabase.table("productos").select("*, categoria:categorias(*)").eq("id", producto_id).single().execute()
        if not full_product_response.data: # Should ideally not happen if previous check passed
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product with ID {producto_id} not found after activity check.")
        return full_product_response.data


    response = await supabase.table("productos").update({"activo": False}).eq("id", producto_id).select("*, categoria:categorias(*)").single().execute()
    
    if not response.data:
        # This case should ideally be covered by the existence check,
        # but as a fallback for unexpected issues:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not soft delete product with ID {producto_id}.",
        )
    return response.data


EXPECTED_EXCEL_COLUMNS = {
    "nombre", # Required
    "descripcion", # Optional
    "precio", # Required, maps to precio_venta
    "stock_disponible", # Required, maps to stock_actual
    "categoria_nombre", # Required
    "codigo_producto" # Optional
}

def normalize_column_name(name: str) -> str:
    return name.lower().replace(" ", "_")

@router.post("/import/", response_model=ImportSummary, status_code=status.HTTP_200_OK)
async def import_products_from_excel(
    *,
    file: UploadFile = File(...),
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user)
) -> Any:
    """
    Import products from an Excel file.
    Expected columns: 'nombre', 'descripcion', 'precio', 'stock_disponible', 'categoria_nombre', 'codigo_producto'.
    """
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file format. Please upload an Excel file (.xlsx or .xls).")

    try:
        contents = await file.read()
        df = pd.read_excel(contents)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error reading Excel file: {str(e)}")

    df.columns = [normalize_column_name(col) for col in df.columns]
    
    # Check for missing essential columns based on normalized names
    missing_cols = [col for col in ["nombre", "precio", "stock_disponible", "categoria_nombre"] if col not in df.columns]
    if missing_cols:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required columns in Excel file after normalization: {', '.join(missing_cols)}. Expected: nombre, precio, stock_disponible, categoria_nombre."
        )

    total_rows = len(df)
    imported_count = 0
    skipped_count = 0
    errors_list: List[Dict[str, Any]] = []

    # Fetch all category names and map them to their IDs for efficient lookup
    categories_response = await supabase.table("categorias").select("id, nombre").execute()
    category_name_to_id_map = {
        normalize_column_name(cat["nombre"]): cat["id"] for cat in categories_response.data
    } if categories_response.data else {}


    for index, row in df.iterrows():
        row_number = index + 2 # Excel rows are 1-based, and header is 1st row
        row_data_dict = row.to_dict()

        try:
            # --- Validation and Data Preparation ---
            nombre_producto = row.get("nombre")
            if pd.isna(nombre_producto) or not nombre_producto:
                errors_list.append({"row_number": row_number, "error": "Missing 'nombre' (product name).", "row_data": row_data_dict})
                skipped_count += 1
                continue
            nombre_producto = str(nombre_producto).strip()

            precio_venta = row.get("precio")
            if pd.isna(precio_venta):
                errors_list.append({"row_number": row_number, "error": "Missing 'precio'.", "row_data": row_data_dict})
                skipped_count += 1
                continue
            try:
                precio_venta = float(precio_venta)
                if precio_venta <= 0:
                    raise ValueError("Price must be positive.")
            except ValueError:
                errors_list.append({"row_number": row_number, "error": "'precio' must be a positive number.", "row_data": row_data_dict})
                skipped_count += 1
                continue

            stock_actual = row.get("stock_disponible")
            if pd.isna(stock_actual):
                errors_list.append({"row_number": row_number, "error": "Missing 'stock_disponible'.", "row_data": row_data_dict})
                skipped_count += 1
                continue
            try:
                stock_actual = int(stock_actual)
                if stock_actual < 0:
                    raise ValueError("Stock must be non-negative.")
            except ValueError:
                errors_list.append({"row_number": row_number, "error": "'stock_disponible' must be a non-negative integer.", "row_data": row_data_dict})
                skipped_count += 1
                continue
            
            categoria_nombre_excel = row.get("categoria_nombre")
            if pd.isna(categoria_nombre_excel) or not categoria_nombre_excel:
                errors_list.append({"row_number": row_number, "error": "Missing 'categoria_nombre'.", "row_data": row_data_dict})
                skipped_count += 1
                continue
            
            normalized_categoria_nombre = normalize_column_name(str(categoria_nombre_excel).strip())
            categoria_id = category_name_to_id_map.get(normalized_categoria_nombre)
            if categoria_id is None:
                errors_list.append({"row_number": row_number, "error": f"Category '{categoria_nombre_excel}' not found.", "row_data": row_data_dict})
                skipped_count += 1
                continue

            codigo_producto = row.get("codigo_producto")
            if pd.notna(codigo_producto) and codigo_producto:
                codigo_producto = str(codigo_producto).strip()
                existing_product_code_response = await supabase.table("productos").select("id").eq("codigo", codigo_producto).execute()
                if existing_product_code_response.data:
                    errors_list.append({"row_number": row_number, "error": f"Product code '{codigo_producto}' already exists.", "row_data": row_data_dict})
                    skipped_count += 1
                    continue
            else:
                codigo_producto = None # Explicitly set to None if not provided or NaN

            descripcion_producto = str(row.get("descripcion", "")).strip() if pd.notna(row.get("descripcion")) else None

            product_to_create_data = {
                "nombre": nombre_producto,
                "descripcion": descripcion_producto,
                "precio_venta": precio_venta,
                "precio_compra": row.get("precio_compra"), # Assuming it might be an optional column
                "stock_actual": stock_actual,
                "stock_minimo": row.get("stock_minimo", 0), # Default to 0 if not present
                "categoria_id": categoria_id,
                "codigo": codigo_producto,
                "activo": True
            }
            
            # Use Pydantic model for final validation before insert
            product_schema = ProductoCreate(**product_to_create_data)

            # --- Product Creation ---
            insert_response = await supabase.table("productos").insert(product_schema.model_dump()).execute()
            if insert_response.data:
                imported_count += 1
            else: # Should ideally capture Supabase error here
                errors_list.append({"row_number": row_number, "error": "Failed to save product to database.", "row_data": row_data_dict})
                skipped_count += 1
        
        except Exception as e_row: # Catch any other unexpected error for this specific row
            errors_list.append({"row_number": row_number, "error": f"Unexpected error processing row: {str(e_row)}", "row_data": row_data_dict})
            skipped_count += 1
            continue

    return ImportSummary(
        total_rows_processed=total_rows,
        successfully_imported_count=imported_count,
        skipped_rows_count=skipped_count,
        errors=errors_list
    )
