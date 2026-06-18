from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from datetime import datetime, date, timedelta
import logging

from app.api.context import BusinessScopedClientDep, ScopedClientContext
from app.dependencies import PermissionDependency
from app.schemas.dashboard import (
    DashboardSummaryResponse, AlertItem, TodaySummary, 
    TrendPoint, TopProduct, LowStockProduct, InventoryHealth
)
from app.services.config_cache import get_negocio_config

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/summary", response_model=DashboardSummaryResponse,
    dependencies=[Depends(PermissionDependency("dashboard", "ver"))]
)
async def get_dashboard_summary(
    business_id: str,
    request: Request,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep)
) -> Any:
    """Get optimized dashboard summary tailored for action and speed."""
    supabase = scoped.client
    branch_id = scoped.context.branch_id
    
    try:
        import pytz
        tz_arg = pytz.timezone("America/Argentina/Buenos_Aires")
        now = datetime.now(tz_arg)
    except Exception:
        now = datetime.now()
        
    today_str = now.strftime('%Y-%m-%d')
    seven_days_ago_str = (now - timedelta(days=6)).strftime('%Y-%m-%d')
    thirty_days_ago_str = (now - timedelta(days=30)).strftime('%Y-%m-%d')
    three_days_ago_str = (now - timedelta(days=3)).strftime('%Y-%m-%d')
    
    status_indicator = "healthy"
    alerts: List[AlertItem] = []
    
    # -------------------------------------------------------------------------
    # 1. Config Check (ARCA & Inventory Mode)
    # -------------------------------------------------------------------------
    config_data = get_negocio_config(business_id, supabase)
    inventario_modo = config_data.get("inventario_modo", "centralizado")
    
    # ARCA Check
    arca_resp = supabase.table("configuracion_fiscal").select("certificado_vencimiento").eq("negocio_id", business_id).execute()
    if arca_resp.data:
        vencimiento = arca_resp.data[0].get("certificado_vencimiento")
        if vencimiento:
            try:
                venc_date = datetime.fromisoformat(vencimiento.replace('Z', '+00:00'))
                if venc_date < now:
                    alerts.append(AlertItem(
                        id="arca_expired",
                        type="arca",
                        message="Tu certificado ARCA está vencido. No podrás emitir facturas.",
                        action_url="/configuracion-fiscal"
                    ))
                    status_indicator = "critical"
            except ValueError:
                pass
        else:
            alerts.append(AlertItem(
                id="arca_missing",
                type="arca",
                message="No tienes configurado el certificado ARCA para facturación electrónica.",
                action_url="/configuracion-fiscal"
            ))
            if status_indicator == "healthy":
                status_indicator = "attention"
    
    # -------------------------------------------------------------------------
    # 2. Sales Trend (Last 7 Days) & Top Products (Last 30 Days)
    # -------------------------------------------------------------------------
    query_ventas = supabase.table("ventas").select("id, total, fecha, venta_detalle(producto_id, cantidad, subtotal)").eq("negocio_id", business_id).gte("fecha", f"{thirty_days_ago_str}T00:00:00")
    if branch_id:
        query_ventas = query_ventas.eq("sucursal_id", branch_id)
        
    ventas_resp = query_ventas.execute()
    all_ventas = ventas_resp.data or []
    
    # Process Sales
    sales_trend_dict = { (now - timedelta(days=i)).strftime('%Y-%m-%d'): 0.0 for i in range(7) }
    today_sales_amount = 0.0
    today_sales_count = 0
    product_sales = {} # product_id -> {"quantity": 0, "revenue": 0.0}
    recent_sales_count = 0
    
    for venta in all_ventas:
        fecha_venta_str = venta["fecha"].split("T")[0]
        monto = float(venta["total"])
        
        # Today's Sales
        if fecha_venta_str == today_str:
            today_sales_amount += monto
            today_sales_count += 1
            
        # Sales Trend (Last 7 Days)
        if fecha_venta_str in sales_trend_dict:
            sales_trend_dict[fecha_venta_str] += monto
            
        # Recent sales check for status
        if fecha_venta_str >= three_days_ago_str:
            recent_sales_count += 1
            
        # Top Products (all ventas in last 30 days)
        for detalle in venta.get("venta_detalle", []):
            pid = detalle.get("producto_id")
            if pid:
                if pid not in product_sales:
                    product_sales[pid] = {"quantity": 0, "revenue": 0.0}
                product_sales[pid]["quantity"] += int(detalle.get("cantidad", 0))
                product_sales[pid]["revenue"] += float(detalle.get("subtotal", 0))

    if recent_sales_count == 0 and status_indicator == "healthy":
        alerts.append(AlertItem(
            id="no_sales",
            type="sales",
            message="No has registrado ventas en los últimos 3 días.",
            action_url="/pos"
        ))
        # Decide if this is attention or critical
        status_indicator = "attention"
        
    sales_trend = [TrendPoint(date=k, amount=v) for k, v in sorted(sales_trend_dict.items())]

    # -------------------------------------------------------------------------
    # 3. Cash Position (Today's Cash Flow)
    # -------------------------------------------------------------------------
    query_movs = supabase.table("movimientos_financieros").select("tipo, monto").eq("negocio_id", business_id).gte("fecha", today_str).lte("fecha", today_str)
    if branch_id:
        query_movs = query_movs.eq("sucursal_id", branch_id)
        
    movs_resp = query_movs.execute()
    
    ingresos = today_sales_amount # Start with sales
    egresos = 0.0
    
    for mov in (movs_resp.data or []):
        if mov["tipo"] == "ingreso":
            ingresos += float(mov["monto"])
        else:
            egresos += float(mov["monto"])
            
    cash_position = ingresos - egresos
    
    # -------------------------------------------------------------------------
    # 4. Inventory Health (Low Stock)
    # -------------------------------------------------------------------------
    low_stock_items = []
    
    if inventario_modo == "por_sucursal" and branch_id:
        # Complex query: join inventario_sucursal with productos
        inv_resp = supabase.table("inventario_sucursal").select("stock_actual, producto_id, productos(nombre, stock_minimo)").eq("negocio_id", business_id).eq("sucursal_id", branch_id).execute()
        
        for item in (inv_resp.data or []):
            prod = item.get("productos")
            if not prod: continue
            
            stock_actual = float(item.get("stock_actual", 0))
            stock_min = float(prod.get("stock_minimo") or 0)
            
            if stock_min > 0 and stock_actual <= stock_min:
                low_stock_items.append({
                    "id": item["producto_id"],
                    "name": prod.get("nombre", "Desconocido"),
                    "current_stock": stock_actual,
                    "min_stock": stock_min
                })
    else:
        # Centralized
        prod_resp = supabase.table("productos").select("id, nombre, stock_actual, stock_minimo").eq("negocio_id", business_id).eq("activo", True).execute()
        for prod in (prod_resp.data or []):
            stock_actual = float(prod.get("stock_actual", 0))
            stock_min = float(prod.get("stock_minimo") or 0)
            if stock_min > 0 and stock_actual <= stock_min:
                low_stock_items.append({
                    "id": prod["id"],
                    "name": prod.get("nombre", "Desconocido"),
                    "current_stock": stock_actual,
                    "min_stock": stock_min
                })
                
    low_stock_items = sorted(low_stock_items, key=lambda x: x["current_stock"] - x["min_stock"])
    
    if len(low_stock_items) > 0:
        if len(low_stock_items) > 3 and status_indicator == "healthy":
            status_indicator = "attention"
        alerts.append(AlertItem(
            id="low_stock",
            type="stock",
            message=f"Tienes {len(low_stock_items)} producto(s) con stock por debajo del mínimo.",
            action_url="/productos"
        ))

    # Get names for Top Products
    top_selling = []
    if product_sales:
        top_pids = sorted(product_sales.keys(), key=lambda k: product_sales[k]["quantity"], reverse=True)[:5]
        
        if top_pids:
            top_prod_resp = supabase.table("productos").select("id, nombre").in_("id", top_pids).execute()
            prod_names = {p["id"]: p.get("nombre", "Desconocido") for p in (top_prod_resp.data or [])}
            
            for pid in top_pids:
                top_selling.append(TopProduct(
                    id=pid,
                    name=prod_names.get(pid, "Desconocido"),
                    quantity=product_sales[pid]["quantity"],
                    revenue=product_sales[pid]["revenue"]
                ))
    
    # -------------------------------------------------------------------------
    # 5. Pending Tasks
    # -------------------------------------------------------------------------
    query_tareas = supabase.table("tareas").select("id").eq("negocio_id", business_id).in_("estado", ["pendiente", "en_progreso"])
    tareas_resp = query_tareas.execute()
    pending_tasks_count = len(tareas_resp.data or [])
    
    if pending_tasks_count > 0:
        alerts.append(AlertItem(
            id="pending_tasks",
            type="task",
            message=f"Tienes {pending_tasks_count} tarea(s) pendiente(s) o en progreso.",
            action_url="/tareas"
        ))

    # Compile Final Response
    return DashboardSummaryResponse(
        status=status_indicator,
        alerts=alerts,
        today_summary=TodaySummary(
            sales_amount=today_sales_amount,
            sales_count=today_sales_count,
            cash_position=cash_position,
            pending_tasks=pending_tasks_count
        ),
        sales_trend=sales_trend,
        inventory_health=InventoryHealth(
            top_selling=top_selling,
            low_stock=[LowStockProduct(**ls) for ls in low_stock_items[:5]]
        )
    )
