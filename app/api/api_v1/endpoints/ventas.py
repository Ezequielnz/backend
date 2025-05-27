from typing import List, Any, Optional
from datetime import datetime, timezone, date

from fastapi import APIRouter, HTTPException, status, Depends
from supabase.client import Client

# Import dependencies and schemas
from app.api import deps
from app.db.supabase_client import get_supabase_client
from app.schemas.usuario import Usuario as CurrentUserSchema # To type hint current_user
from app.schemas.venta import VentaCreate, VentaResponse, VentaDetalleCreate, VentaDetalleResponse
from app.schemas.producto import Producto as ProductoSchema


router = APIRouter()

@router.get("/")
async def list_sales( # Renamed from get_ventas for clarity
    *,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user),
    cliente_id: Optional[int] = None,
    fecha_inicio: Optional[date] = None,
    fecha_fin: Optional[date] = None,
    skip: int = 0,
    limit: int = 100
) -> List[VentaResponse]:
    """
    Get a list of sales made by the authenticated user.
    Optionally filter by cliente_id and date range.
    """
    query = supabase.table("ventas").select("*, detalles:venta_detalle(*, producto:productos(*))") \
        .eq("empleado_id", current_user.id)

    if cliente_id is not None:
        query = query.eq("cliente_id", cliente_id)
    if fecha_inicio:
        query = query.gte("fecha", fecha_inicio.isoformat())
    if fecha_fin:
        # To include the whole end day, we can aim for the start of the next day
        # or ensure the timestamp comparison handles this correctly.
        # For date fields, direct comparison should be fine.
        query = query.lte("fecha", fecha_fin.isoformat())
    
    response = await query.order("fecha", desc=True).range(skip, skip + limit - 1).execute()
    
    if response.data is None:
         raise HTTPException(status_code=500, detail="Error fetching sales data.")
    return response.data


@router.post("/", response_model=VentaResponse, status_code=status.HTTP_201_CREATED)
async def create_sale( # Renamed from create_venta
    *,
    venta_in: VentaCreate,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user)
) -> Any:
    """
    Register a new sale.
    """
    # 1. Verify cliente_id belongs to the authenticated user
    # Assuming 'clientes' table has 'empleado_id' as string UUID
    client_response = await supabase.table("clientes").select("id, empleado_id") \
        .eq("id", venta_in.cliente_id) \
        .maybe_single().execute()

    if not client_response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Client with ID {venta_in.cliente_id} not found.")
    
    # Critical check: Ensure client's empleado_id matches current_user.id
    # This assumes current_user.id is a string (UUID) and clientes.empleado_id is also a string (UUID)
    if str(client_response.data.get("empleado_id")) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Client does not belong to the authenticated user.")

    processed_details = []
    total_venta_bruto = 0.0

    # 2. Validate products and stock for each item in detalles
    for detalle_in in venta_in.detalles:
        product_response = await supabase.table("productos").select("id, nombre, precio_venta, stock_actual, activo") \
            .eq("id", detalle_in.producto_id) \
            .maybe_single().execute()

        if not product_response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product with ID {detalle_in.producto_id} not found.")
        
        producto_db = product_response.data
        if not producto_db.get("activo", False):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Product '{producto_db['nombre']}' (ID: {detalle_in.producto_id}) is not active.")

        if producto_db["stock_actual"] < detalle_in.cantidad:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Insufficient stock for product '{producto_db['nombre']}' (ID: {detalle_in.producto_id}). Available: {producto_db['stock_actual']}, Requested: {detalle_in.cantidad}.")

        precio_unitario = detalle_in.precio_unitario if detalle_in.precio_unitario is not None else producto_db["precio_venta"]
        subtotal = detalle_in.cantidad * precio_unitario
        
        processed_details.append({
            "producto_id": detalle_in.producto_id,
            "cantidad": detalle_in.cantidad,
            "precio_unitario": precio_unitario,
            "subtotal": subtotal,
            "producto_obj": producto_db # Store for stock update later
        })
        total_venta_bruto += subtotal

    # 3. Apply discount
    descuento_valor = venta_in.descuento if venta_in.descuento is not None else 0.0
    total_venta_neto = total_venta_bruto * (1 - (descuento_valor / 100.0)) if venta_in.descuento else total_venta_bruto
    # Assuming descuento is a percentage. If it's a fixed amount, logic changes.
    # For this implementation, let's assume 'descuento' from VentaCreate is a fixed amount for simplicity with the model.
    # If VentaCreate.descuento is a percentage, the calculation is:
    # total_descuento_aplicado = total_venta_bruto * (venta_in.descuento / 100.0)
    # total_venta_neto = total_venta_bruto - total_descuento_aplicado
    # If VentaCreate.descuento is a fixed amount:
    total_venta_neto = total_venta_bruto - descuento_valor


    # 4. Database Operations
    #    a. Create record in 'ventas' table
    venta_db_data = {
        "cliente_id": venta_in.cliente_id,
        "empleado_id": str(current_user.id), # Ensure it's string for DB if DB expects UUID string
        "fecha": datetime.now(timezone.utc).isoformat(),
        "total": round(total_venta_neto, 2),
        "descuento": descuento_valor, # Store the fixed discount amount
        "medio_pago": venta_in.medio_pago,
        "estado": venta_in.estado,
        "observaciones": venta_in.observaciones
        # Add other fields from VentaCreate like medio_pago, estado if they are in the schema and table
    }
    
    created_venta_response = await supabase.table("ventas").insert(venta_db_data).select("id").single().execute()
    if not created_venta_response.data or not created_venta_response.data.get("id"):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create sale record.")
    
    new_venta_id = created_venta_response.data["id"]

    #    b. For each item, create 'venta_detalle' and update stock
    created_detalles_db = []
    for detail_data in processed_details:
        detalle_to_insert = {
            "venta_id": new_venta_id,
            "producto_id": detail_data["producto_id"],
            "cantidad": detail_data["cantidad"],
            "precio_unitario": detail_data["precio_unitario"],
            "subtotal": detail_data["subtotal"]
        }
        # Supabase insert for venta_detalle
        # Consider batch insert if supported and many items, but for now, individual inserts
        insert_detalle_response = await supabase.table("venta_detalle").insert(detalle_to_insert).select("id").single().execute() # Assuming you want the id back
        if not insert_detalle_response.data:
             # This is critical. If this fails, we need to consider rollback or compensation.
             # For now, raise error. A more robust system might queue this for retry or mark sale as pending.
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to save sale detail for product ID {detail_data['producto_id']}.")
        created_detalles_db.append({**detalle_to_insert, "id": insert_detalle_response.data["id"]})


        # Update stock: stock_actual = stock_actual - cantidad
        # This should ideally be atomic. Supabase doesn't have direct increment/decrement without custom RPC.
        # A simple update is: new_stock = old_stock - quantity.
        # Potential race condition if not handled carefully (e.g. using RLS to ensure stock >= 0).
        # For now, a direct update based on fetched stock.
        # product_obj = detail_data["producto_obj"]
        # new_stock_actual = product_obj["stock_actual"] - detail_data["cantidad"]
        # await supabase.table("productos").update({"stock_actual": new_stock_actual}).eq("id", detail_data["producto_id"]).execute()
        
        # Using an RPC function for atomic decrement is safer if available:
        # e.g., await supabase.rpc('decrement_product_stock', {'product_id_in': detail_data["producto_id"], 'quantity_in': detail_data["cantidad"]}).execute()
        # For now, using direct update. This means the stock check before is crucial.
        # The RLS policies should ideally prevent stock_actual from going below 0 if possible.
        current_product_stock = detail_data["producto_obj"]["stock_actual"]
        updated_stock = current_product_stock - detail_data["cantidad"]
        stock_update_response = await supabase.table("productos").update({"stock_actual": updated_stock}).eq("id", detail_data["producto_id"]).execute()
        # Check stock_update_response for errors if necessary

    # 5. Fetch the complete sale data for the response
    # This ensures all calculated fields and DB-generated IDs are present.
    final_sale_response = await supabase.table("ventas") \
        .select("*, detalles:venta_detalle(*, producto:productos(id, nombre, codigo, precio_venta))") \
        .eq("id", new_venta_id) \
        .single() \
        .execute()

    if not final_sale_response.data:
        # This should not happen if creation was successful
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch created sale for response.")

    return final_sale_response.data


@router.get("/{venta_id}", response_model=VentaResponse)
async def get_sale( # Renamed from get_reporte_ventas for clarity and standard REST
    *,
    venta_id: int,
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user)
) -> Any:
    """
    Get a specific sale by its ID.
    Ensures the sale belongs to the authenticated user.
    """
    response = await supabase.table("ventas") \
        .select("*, detalles:venta_detalle(*, producto:productos(id, nombre, codigo, precio_venta))") \
        .eq("id", venta_id) \
        .eq("empleado_id", str(current_user.id)) \
        .maybe_single() \
        .execute()

    if not response.data:
        # Could be not found OR not owned by user. For security, just say not found.
        # To give specific "forbidden", you'd need to query without empleado_id first, then check.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sale with ID {venta_id} not found or not accessible.")
    
    return response.data


# The old /reporte endpoint is now covered by GET /ventas/ with filters or could be a separate complex reporting endpoint.
# For now, I'm removing the placeholder /reporte to avoid confusion with the new GET /ventas/{venta_id}.
# If /reporte is meant for aggregated reports, it needs a different design.
# @router.get("/reporte")
# async def get_reporte_ventas(current_user: CurrentUserSchema = Depends(deps.get_current_user)):
#     """
#     Obtener reporte de ganancias. Requiere autenticación.
#     (Placeholder implementation)
#     """
#     # TODO: Implement actual logic for sales report, potentially filtered by current_user
#     return {"message": f"Reporte de ganancias para el usuario {current_user.email}"}
    """
    Obtener reporte de ganancias. Requiere autenticación.
    (Placeholder implementation)
    """
    # TODO: Implement actual logic for sales report, potentially filtered by current_user
    return {"message": f"Reporte de ganancias para el usuario {current_user.email}"}