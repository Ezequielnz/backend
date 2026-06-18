from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from datetime import datetime, date, timedelta
import logging

from app.api.context import BusinessScopedClientDep, ScopedClientContext

from app.schemas.dashboard import (
    DashboardSummaryResponse, AlertItem, TodaySummary, 
    TrendPoint, TopProduct, LowStockProduct, InventoryHealth
)
from app.services.config_cache import get_negocio_config

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/summary", response_model=DashboardSummaryResponse)
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
    arca_resp = supabase.table("configuracion_fiscal").select("habilitada, cert_path").eq("negocio_id", business_id).execute()
    if arca_resp.data:
        config = arca_resp.data[0]
        if not config.get("habilitada") or not config.get("cert_path"):
            alerts.append(AlertItem(
                id="arca_missing",
                type="arca",
                message="No tienes configurado el certificado ARCA o la facturación está deshabilitada.",
                action_url="/settings/facturacion"
            ))
            if status_indicator == "healthy":
                status_indicator = "attention"
    else:
        alerts.append(AlertItem(
            id="arca_missing",
            type="arca",
            message="No tienes configurado el certificado ARCA para facturación electrónica.",
            action_url="/settings/facturacion"
        ))
        if status_indicator == "healthy":
            status_indicator = "attention"
    
    # -------------------------------------------------------------------------
    # 2. Sales Trend (Last 7 Days) & Top Products (Last 30 Days)
    # -------------------------------------------------------------------------
    # Fetch Top Products via RPC
    top_selling = []
    top_prod_resp = supabase.rpc(
        "get_dashboard_top_products",
        {"p_negocio_id": business_id, "p_sucursal_id": branch_id, "p_start_date": thirty_days_ago_str}
    ).execute()
    
    for tp in (top_prod_resp.data or []):
        top_selling.append(TopProduct(
            id=tp["producto_id"],
            name=tp["nombre"],
            quantity=int(tp["total_cantidad"]),
            revenue=float(tp["total_ingresos"])
        ))

    # Fetch Sales Trend via RPC
    trend_resp = supabase.rpc(
        "get_dashboard_sales_trend",
        {"p_negocio_id": business_id, "p_sucursal_id": branch_id, "p_start_date": seven_days_ago_str}
    ).execute()
    
    trend_data = trend_resp.data or []
    # Fill missing days with 0
    sales_trend_dict = { (now - timedelta(days=i)).strftime('%Y-%m-%d'): 0.0 for i in range(7) }
    for t in trend_data:
        sales_trend_dict[t["sale_date"]] = float(t["daily_total"])
    sales_trend = [TrendPoint(date=k, amount=v) for k, v in sorted(sales_trend_dict.items())]

    # Check recent sales (last 3 days)
    recent_sales_resp = supabase.table("ventas").select("id").eq("negocio_id", business_id).gte("fecha", f"{three_days_ago_str}T00:00:00").limit(1).execute()
    if not recent_sales_resp.data and status_indicator == "healthy":
        alerts.append(AlertItem(
            id="no_sales",
            type="sales",
            message="No has registrado ventas en los últimos 3 días.",
            action_url="/pos"
        ))
        status_indicator = "attention"
        
    # Today's Sales via RPC
    today_sales_resp = supabase.rpc(
        "get_dashboard_sales_today",
        {"p_negocio_id": business_id, "p_sucursal_id": branch_id, "p_target_date": today_str}
    ).execute()
    
    today_sales_amount = 0.0
    today_sales_count = 0
    if today_sales_resp.data:
        today_sales_amount = float(today_sales_resp.data[0].get("total_sales") or 0.0)
        today_sales_count = int(today_sales_resp.data[0].get("sales_count") or 0)

    # -------------------------------------------------------------------------
    # 3. Cash Position (Today's Cash Flow)
    # -------------------------------------------------------------------------
    cash_flow_resp = supabase.rpc(
        "get_dashboard_cash_flow_today",
        {"p_negocio_id": business_id, "p_sucursal_id": branch_id, "p_target_date": today_str}
    ).execute()
    
    ingresos = today_sales_amount # Start with sales
    egresos = 0.0
    
    for mov in (cash_flow_resp.data or []):
        if mov["tipo"] == "ingreso":
            ingresos += float(mov["total"])
        else:
            egresos += float(mov["total"])
            
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
            action_url="/products-and-services"
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
            action_url="/tasks"
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
