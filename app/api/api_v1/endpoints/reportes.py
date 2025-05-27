from typing import List, Any, Dict, Optional
from datetime import datetime, date, timedelta
from collections import defaultdict
import itertools # For groupby

from fastapi import APIRouter, Depends, HTTPException, status
from supabase.client import Client

from app.db.supabase_client import get_supabase_client
from app.api import deps
from app.schemas.usuario import Usuario as CurrentUserSchema
from app.schemas.reporte import ReporteQueryParams, VentaPorPeriodo, ReporteVentasResponse

router = APIRouter()

@router.get("/ventas_y_ganancias/", response_model=ReporteVentasResponse)
async def get_sales_and_profit_report(
    *,
    params: ReporteQueryParams = Depends(),
    supabase: Client = Depends(get_supabase_client),
    current_user: CurrentUserSchema = Depends(deps.get_current_user)
) -> Any:
    """
    Generate a sales and profit report for the authenticated user,
    aggregated daily or monthly within the specified date range.
    """
    # Adjust fecha_fin to include the whole day
    fecha_fin_adjusted = params.fecha_fin + timedelta(days=1)

    # 1. Fetch sales data with details and product costs
    # This query fetches all sales for the user, then filters by date in Python.
    # For very large datasets, filtering by date in the DB query would be better.
    # Supabase date filtering: .gte('fecha', params.fecha_inicio.isoformat()).lt('fecha', fecha_fin_adjusted.isoformat())
    
    sales_response = await supabase.table("ventas") \
        .select("id, fecha, total, descuento, detalles:venta_detalle(*, producto:productos(id, nombre, precio_compra))") \
        .eq("empleado_id", str(current_user.id)) \
        .gte("fecha", params.fecha_inicio.isoformat()) \
        .lt("fecha", fecha_fin_adjusted.isoformat()) \
        .order("fecha", desc=False) \
        .execute()

    if sales_response.data is None: # Should be data=[] if no sales, or error object if issue
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching sales data.")

    # Prepare data for aggregation
    period_data = defaultdict(lambda: {"total_ventas": 0.0, "total_ganancia": 0.0, "numero_ventas": 0, "has_profit_data": True})
    
    # Define date formatting based on grouping
    if params.agrupar_por == "dia":
        get_period_key = lambda d: d.strftime("%Y-%m-%d")
    elif params.agrupar_por == "mes":
        get_period_key = lambda d: d.strftime("%Y-%m")
    else: # Should not happen due to Pydantic validation, but as a fallback
        get_period_key = lambda d: d.strftime("%Y-%m-%d")


    for venta in sales_response.data:
        try:
            # Ensure 'fecha' is a datetime object if it's a string
            if isinstance(venta["fecha"], str):
                venta_fecha = datetime.fromisoformat(venta["fecha"].replace("Z", "+00:00")).date()
            elif isinstance(venta["fecha"], datetime):
                venta_fecha = venta["fecha"].date()
            else: # Should not happen with Supabase datetime fields
                continue 
        except ValueError: # Handle potential parsing errors for date
            continue

        period_key = get_period_key(venta_fecha)
        
        # Venta total is already calculated for the sale, including discounts
        # The 'total' field in the 'ventas' table is assumed to be the final sale amount after discounts.
        period_data[period_key]["total_ventas"] += venta.get("total", 0.0)
        period_data[period_key]["numero_ventas"] += 1
        
        current_venta_ganancia = 0.0
        venta_has_all_profit_data = True

        if venta.get("detalles"):
            for detalle in venta["detalles"]:
                producto = detalle.get("producto")
                if producto and producto.get("precio_compra") is not None:
                    costo_item = producto["precio_compra"] * detalle["cantidad"]
                    # 'subtotal' on venta_detalle should be (precio_unitario * cantidad) before any sale-level discount
                    # Assuming detalle['subtotal'] is (detalle.precio_unitario * detalle.cantidad)
                    # If 'total' on 'ventas' already reflects discounts, profit calculation needs care.
                    # For simplicity, let's assume ganancia per item is based on its *actual selling price contribution*
                    # If 'ventas.total' is sum of 'venta_detalle.subtotal' - 'ventas.descuento', then:
                    # proportion_of_total = detalle['subtotal'] / sum(d['subtotal'] for d in venta['detalles']) if sum > 0 else 0
                    # effective_selling_price_for_item = detalle['subtotal'] - (venta.get('descuento',0) * proportion_of_total)
                    # ganancia_item = effective_selling_price_for_item - costo_item
                    # This gets complex. A simpler approach:
                    # Profit per item = (detalle.precio_unitario * detalle.cantidad) - (producto.precio_compra * detalle.cantidad)
                    # Sum these up, then subtract the overall sale discount proportionally or ignore its effect on itemized profit.
                    # Let's use: (detalle.precio_unitario * detalle.cantidad) - (producto.precio_compra * detalle.cantidad)
                    # This is: detalle.subtotal - (producto.precio_compra * detalle.cantidad)
                    
                    ganancia_item = detalle["subtotal"] - (producto["precio_compra"] * detalle["cantidad"])
                    current_venta_ganancia += ganancia_item
                else:
                    venta_has_all_profit_data = False # Missing cost for at least one item in this sale
                    break # Stop calculating profit for this sale if any item is missing cost
            
            if venta_has_all_profit_data:
                period_data[period_key]["total_ganancia"] += current_venta_ganancia
            else:
                # If any item in a sale is missing profit data, the entire sale's profit is compromised for accuracy.
                # Mark the period as not having full profit data.
                period_data[period_key]["has_profit_data"] = False


    # Convert defaultdict to list of VentaPorPeriodo
    resumen_list: List[VentaPorPeriodo] = []
    total_general_ventas = 0.0
    total_general_ganancia_val = 0.0
    profit_calculable_for_all_periods = True

    sorted_periods = sorted(period_data.keys())

    for period_key in sorted_periods:
        data = period_data[period_key]
        total_general_ventas += data["total_ventas"]
        
        current_period_ganancia = None
        if data["has_profit_data"]:
            current_period_ganancia = data["total_ganancia"]
            total_general_ganancia_val += data["total_ganancia"]
        else:
            profit_calculable_for_all_periods = False # If one period is missing full profit, overall total is also affected

        resumen_list.append(
            VentaPorPeriodo(
                periodo=period_key,
                total_ventas=round(data["total_ventas"], 2),
                total_ganancia=round(current_period_ganancia, 2) if current_period_ganancia is not None else None,
                numero_ventas=data["numero_ventas"]
            )
        )

    final_total_general_ganancia = round(total_general_ganancia_val, 2) if profit_calculable_for_all_periods else None
    
    return ReporteVentasResponse(
        resumen=resumen_list,
        total_general_ventas=round(total_general_ventas, 2),
        total_general_ganancia=final_total_general_ganancia,
        filtros={
            "fecha_inicio": params.fecha_inicio.isoformat(),
            "fecha_fin": params.fecha_fin.isoformat(),
            "agrupar_por": params.agrupar_por
        }
    )
