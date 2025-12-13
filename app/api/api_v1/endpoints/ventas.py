import logging
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header, Query
from datetime import datetime, date, timedelta
import calendar
from pydantic import BaseModel, Field
import uuid
import jwt
import json
import time
import asyncio

from app.db.supabase_client import get_supabase_user_client
from app.db.scoped_client import get_scoped_supabase_user_client
from app.dependencies import PermissionDependency
from app.api.context import BusinessBranchContextDep
from app.core.permissions import check_subscription_access

logger = logging.getLogger(__name__)

router = APIRouter()
branch_router = APIRouter()

def get_user_id_from_token(token: str) -> str:
    """
    Extrae el user_id del token JWT de Supabase.
    """
    try:
        # Remover 'Bearer ' si está presente
        if token.startswith('Bearer '):
            token = token[7:]
        
        # Decodificar el JWT sin verificar la firma (solo para obtener el payload)
        # En producción, deberías verificar la firma con la clave pública de Supabase
        decoded = jwt.decode(token, options={"verify_signature": False})
        
        # El user_id está en el campo 'sub' del JWT
        user_id = decoded.get('sub')
        if not user_id:
            raise HTTPException(status_code=401, detail="Token JWT inválido: no contiene user_id")
        
        return user_id
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Error al procesar token: {str(e)}")

# Pydantic models for request/response
class VentaItemCreate(BaseModel):
    producto_id: str
    cantidad: int = Field(gt=0, description="Cantidad debe ser mayor a 0")
    precio_unitario: float = Field(gt=0, description="Precio unitario debe ser mayor a 0")
    subtotal: float = Field(gt=0, description="Subtotal debe ser mayor a 0")

class VentaCreate(BaseModel):
    cliente_id: Optional[str] = None
    metodo_pago: str = Field(..., description="Método de pago: efectivo, tarjeta, transferencia")
    total: float = Field(gt=0, description="Total debe ser mayor a 0")
    items: List[VentaItemCreate] = Field(..., description="Debe incluir al menos un item")
    observaciones: Optional[str] = None

class VentaResponse(BaseModel):
    id: str
    negocio_id: str
    cliente_id: Optional[str]
    metodo_pago: str
    total: float
    fecha: datetime
    observaciones: Optional[str]
    items: List[dict]

class VentaEstadisticas(BaseModel):
    total_ventas: int
    total_ingresos: float
    venta_promedio: float
    ventas_hoy: int
    ingresos_hoy: float

class DashboardStats(BaseModel):
    totalProducts: int
    totalCustomers: int
    totalSales: int
    monthlyRevenue: float
    lowStockProducts: int
    pendingOrders: int

class VentaItem(BaseModel):
    id: str  # producto_id
    tipo: str  # "producto" o "servicio"
    cantidad: int
    precio: float

class VentaRequest(BaseModel):
    items: List[VentaItem]
    cliente_id: Optional[str] = None
    metodo_pago: str  # Mantenemos metodo_pago en la API pero lo mapeamos a medio_pago
    observaciones: Optional[str] = None

class VentaResponseSimple(BaseModel):
    id: str
    total: float
    fecha: str  # Supabase devuelve fecha como string
    mensaje: str

class DashboardStatsPeriod(BaseModel):
    total_sales: float
    estimated_profit: float
    new_customers: int

class DashboardStatsResponse(BaseModel):
    today: DashboardStatsPeriod
    week: DashboardStatsPeriod
    month: DashboardStatsPeriod
    top_items: List[dict]
    # Nuevos campos para el dashboard
    total_products: int
    total_customers: int
    low_stock_products: int


class DashboardSalesWindowRow(BaseModel):
    date: date
    total: float
    cost: float
    profit: float
    customers: int
    orders: int


class DashboardSalesWindowResponse(BaseModel):
    rows: List[DashboardSalesWindowRow]
    next_cursor: Optional[str]
    page: int
    page_size: int

@branch_router.post("/record-sale", response_model=VentaResponseSimple)
async def record_sale_branch(
    business_id: str,
    branch_id: str,
    venta_data: VentaRequest,
    request: Request,
    authorization: str = Header(..., description="Bearer token"),
    subscription_check: bool = Depends(check_subscription_access)
):
    """
    Registra una nueva venta de forma branch-scoped (requiere business_id y branch_id).
    Valida pertenencia del usuario al negocio (usuarios_negocios) y a la sucursal (usuarios_sucursales).
    """
    try:
        client = get_scoped_supabase_user_client(authorization, business_id, branch_id)
        user_id = get_user_id_from_token(authorization)

        # Validate business and branch via dependency
        context = await BusinessBranchContextDep(request, business_id, branch_id)
        usuario_negocio_id = context.usuario_negocio_id

        # Normalizar cliente_id (opcional)
        cliente_id = venta_data.cliente_id.strip() if isinstance(venta_data.cliente_id, str) else venta_data.cliente_id
        if cliente_id == "":
            cliente_id = None
        if cliente_id:
            cliente_response = (
                client.table("clientes")
                .select("id")
                .eq("id", cliente_id)
                .eq("negocio_id", business_id)
                .execute()
            )
            if not cliente_response.data:
                raise HTTPException(
                    status_code=404,
                    detail=f"Cliente {cliente_id} no encontrado o no pertenece al negocio {business_id}"
                )

        # Calcular total y validar stock de productos
        total = 0.0
        items_validados = []

        for item in venta_data.items:
            if item.tipo == "producto":
                producto_response = (
                    client.table("productos")
                    .select("id, nombre, precio_venta, stock_actual")
                    .eq("id", item.id)
                    .eq("negocio_id", business_id)
                    .execute()
                )
                if not producto_response.data:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Producto {item.id} no encontrado o no pertenece al negocio {business_id}"
                    )

                producto = producto_response.data[0]
                if producto["stock_actual"] < item.cantidad:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Stock insuficiente para {producto['nombre']}. Stock disponible: {producto['stock_actual']}"
                    )

                subtotal = item.cantidad * item.precio
                total += subtotal

                items_validados.append({
                    "producto_id": item.id,
                    "servicio_id": None,
                    "tipo": "producto",
                    "cantidad": item.cantidad,
                    "precio_unitario": item.precio,
                    "subtotal": subtotal,
                    "sucursal_id": branch_id
                })

            elif item.tipo == "servicio":
                servicio_response = (
                    client.table("servicios")
                    .select("id, nombre, precio")
                    .eq("id", item.id)
                    .eq("negocio_id", business_id)
                    .execute()
                )
                if not servicio_response.data:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Servicio {item.id} no encontrado o no pertenece al negocio {business_id}"
                    )

                subtotal = item.cantidad * item.precio
                total += subtotal

                items_validados.append({
                    "producto_id": None,
                    "servicio_id": item.id,
                    "tipo": "servicio",
                    "cantidad": item.cantidad,
                    "precio_unitario": item.precio,
                    "subtotal": subtotal,
                    "sucursal_id": branch_id
                })

        # Insertar venta con negocio y sucursal explícitos
        venta_id = str(uuid.uuid4())
        venta_insert_data = {
            "id": venta_id,
            "negocio_id": business_id,
            "sucursal_id": branch_id,
            "cliente_id": cliente_id,
            "usuario_negocio_id": usuario_negocio_id,
            "total": total,
            "medio_pago": venta_data.metodo_pago,
            "fecha": datetime.now().isoformat(),
            "observaciones": venta_data.observaciones
        }

        venta_response = client.table("ventas").insert(venta_insert_data).execute()
        if not venta_response.data:
            raise HTTPException(status_code=500, detail="Error al crear la venta")

        # Insertar detalles de venta
        for item in items_validados:
            item["venta_id"] = venta_id

        detalle_response = client.table("venta_detalle").insert(items_validados).execute()
        if not detalle_response.data:
            # Rollback: eliminar la venta creada si fallan los detalles
            client.table("ventas").delete().eq("id", venta_id).execute()
            raise HTTPException(status_code=500, detail="Error al crear los detalles de venta")

        # Actualizar stock global de productos (modelo actual, inventario por sucursal vendrá luego)
        for item in venta_data.items:
            if item.tipo == "producto":
                producto_response = (
                    client.table("productos")
                    .select("stock_actual")
                    .eq("id", item.id)
                    .eq("negocio_id", business_id)
                    .execute()
                )
                if producto_response.data:
                    stock_actual = producto_response.data[0]["stock_actual"]
                    nuevo_stock = stock_actual - item.cantidad
                    client.table("productos").update({
                        "stock_actual": nuevo_stock
                    }).eq("id", item.id).eq("negocio_id", business_id).execute()

        venta_creada = venta_response.data[0]
        return VentaResponseSimple(
            id=venta_creada["id"],
            total=venta_creada["total"],
            fecha=venta_creada["fecha"],
            mensaje="Venta registrada exitosamente (branch-scoped)"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.post("/record-sale", response_model=VentaResponseSimple)
async def record_sale(
    venta_data: VentaRequest,
    request: Request,
    authorization: str = Header(..., description="Bearer token"),
    subscription_check: bool = Depends(check_subscription_access)
):
    """
    Registra una nueva venta y actualiza el stock de productos.
    """
    try:
        # Obtener cliente autenticado
        client = get_supabase_user_client(authorization)
        
        # Obtener el user_id del usuario autenticado
        user_id = get_user_id_from_token(authorization)
        
        # Obtener el negocio asociado del usuario autenticado
        usuario_negocio_response = (
            client
            .table("usuarios_negocios")
            .select("id, negocio_id")
            .eq("usuario_id", user_id)
            .eq("estado", "aceptado")
            .limit(1)
            .execute()
        )
        
        if not usuario_negocio_response.data:
            raise HTTPException(status_code=403, detail="Usuario no tiene acceso a ningún negocio")
        
        usuario_negocio_id = usuario_negocio_response.data[0]["id"]
        negocio_id = usuario_negocio_response.data[0]["negocio_id"]
        
        # Normalizar cliente_id: permitir None o string vacío y validar solo si existe
        cliente_id = venta_data.cliente_id.strip() if isinstance(venta_data.cliente_id, str) else venta_data.cliente_id
        if cliente_id == "":
            cliente_id = None
        if cliente_id:
            cliente_response = client.table("clientes").select("id").eq("id", cliente_id).eq("negocio_id", negocio_id).execute()
            
            if not cliente_response.data:
                raise HTTPException(status_code=404, detail=f"Cliente {cliente_id} no encontrado o no pertenece al negocio {negocio_id}")
        
        # Calcular total y validar stock
        total = 0.0
        items_validados = []
        
        for item in venta_data.items:
            if item.tipo == "producto":
                # Verificar que el producto existe y tiene stock suficiente
                producto_response = client.table("productos").select("id, nombre, precio_venta, stock_actual").eq("id", item.id).eq("negocio_id", negocio_id).execute()
                
                if not producto_response.data:
                    raise HTTPException(status_code=404, detail=f"Producto {item.id} no encontrado o no pertenece al negocio {negocio_id}")
                
                producto = producto_response.data[0]
                
                if producto["stock_actual"] < item.cantidad:
                    raise HTTPException(status_code=400, detail=f"Stock insuficiente para {producto['nombre']}. Stock disponible: {producto['stock_actual']}")
                
                subtotal = item.cantidad * item.precio
                total += subtotal
                
                items_validados.append({
                    "producto_id": item.id,
                    "servicio_id": None,
                    "tipo": "producto",
                    "cantidad": item.cantidad,
                    "precio_unitario": item.precio,
                    "subtotal": subtotal
                })
                
            elif item.tipo == "servicio":
                # Los servicios no requieren validación de stock
                # Verificar que el servicio existe
                servicio_response = client.table("servicios").select("id, nombre, precio").eq("id", item.id).eq("negocio_id", negocio_id).execute()
                
                if not servicio_response.data:
                    raise HTTPException(status_code=404, detail=f"Servicio {item.id} no encontrado o no pertenece al negocio {negocio_id}")
                
                subtotal = item.cantidad * item.precio
                total += subtotal
                
                items_validados.append({
                    "producto_id": None,
                    "servicio_id": item.id,
                    "tipo": "servicio",
                    "cantidad": item.cantidad,
                    "precio_unitario": item.precio,
                    "subtotal": subtotal
                })
        
        # Crear la venta
        venta_id = str(uuid.uuid4())
        venta_insert_data = {
            "id": venta_id,
            "negocio_id": negocio_id,
            "cliente_id": cliente_id,
            "usuario_negocio_id": usuario_negocio_id,  # Agregar el usuario_negocio_id
            "total": total,
            "medio_pago": venta_data.metodo_pago,  # Mapear metodo_pago a medio_pago
            "fecha": datetime.now().isoformat(),
            "observaciones": venta_data.observaciones
        }

        # Verificar descuento por método de pago
        metodo_pago_response = client.table("metodos_pago").select("descuento_porcentaje").eq("negocio_id", negocio_id).eq("nombre", venta_data.metodo_pago).eq("activo", True).execute()
        if metodo_pago_response.data:
            descuento_pct = metodo_pago_response.data[0]["descuento_porcentaje"]
            if descuento_pct > 0:
                descuento_monto = total * (descuento_pct / 100)
                venta_insert_data["total"] = total - descuento_monto
                # Agregar nota sobre descuento
                nota_descuento = f" (Descuento {descuento_pct}% aplicado: ${descuento_monto:.2f})"
                if venta_insert_data["observaciones"]:
                    venta_insert_data["observaciones"] += nota_descuento
                else:
                    venta_insert_data["observaciones"] = nota_descuento.strip()
        
        # Insertar la venta (cada venta debe ser única)
        venta_response = client.table("ventas").insert(venta_insert_data).execute()
        
        if not venta_response.data:
            raise HTTPException(status_code=500, detail="Error al crear la venta")
        
        venta_creada = venta_response.data[0]
        
        # Crear los detalles de venta
        for item in items_validados:
            item["venta_id"] = venta_id
            
        detalle_response = client.table("venta_detalle").insert(items_validados).execute()
        
        if not detalle_response.data:
            # Rollback: eliminar la venta creada
            client.table("ventas").delete().eq("id", venta_id).execute()
            raise HTTPException(status_code=500, detail="Error al crear los detalles de venta")
        
        # Actualizar stock de productos
        for item in venta_data.items:
            if item.tipo == "producto":
                # Obtener stock actual del producto
                producto_response = (
                    client
                    .table("productos")
                    .select("stock_actual")
                    .eq("id", item.id)
                    .eq("negocio_id", negocio_id)
                    .execute()
                )
                if producto_response.data:
                    stock_actual = producto_response.data[0]["stock_actual"]
                    nuevo_stock = stock_actual - item.cantidad
                    
                    # Reducir stock
                    client.table("productos").update({
                        "stock_actual": nuevo_stock
                    }).eq("id", item.id).eq("negocio_id", negocio_id).execute()
        
        return VentaResponseSimple(
            id=venta_creada["id"],
            total=venta_creada["total"],
            fecha=venta_creada["fecha"],
            mensaje="Venta registrada exitosamente"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.get("/sales")
async def get_sales(
    business_id: str,
    request: Request,
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None,
):
    """
    Obtiene todas las ventas del negocio indicado, opcionalmente filtradas por fecha.
    """
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación requerido"
        )
    try:
        client = get_scoped_supabase_user_client(token, business_id)

        # Construir consulta con filtros opcionales
        query = client.table("ventas").select("""
            id,
            cliente_id,
            fecha,
            total,
            medio_pago,
            estado,
            observaciones,
            clientes (
                nombre,
                email
            )
        """).eq("negocio_id", business_id).order("fecha", desc=True)

        if fecha_inicio:
            query = query.gte("fecha", fecha_inicio)
        if fecha_fin:
            query = query.lte("fecha", fecha_fin)

        ventas_response = query.execute()

        data = ventas_response.data if ventas_response.data else []
        return {
            "ventas": data,
            "total_ventas": len(data)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener ventas: {str(e)}")

@router.get("/sales/{venta_id}")
async def get_sale_detail(
    business_id: str,
    venta_id: str,
    authorization: str = Header(..., description="Bearer token")
):
    """
    Obtiene el detalle de una venta específica.
    """
    try:
        client = get_scoped_supabase_user_client(authorization, business_id)
        
        # Obtener venta con detalles
        venta_response = client.table("ventas").select("""
            id,
            fecha,
            total,
            medio_pago,
            estado,
            observaciones,
            clientes (
                nombre,
                email,
                telefono
            )
        """).eq("id", venta_id).execute()
        
        if not venta_response.data:
            raise HTTPException(status_code=404, detail="Venta no encontrada")
        
        # Obtener detalles de la venta
        detalle_response = client.table("venta_detalle").select("""
            cantidad,
            precio_unitario,
            subtotal,
            descuento,
            tipo,
            productos (
                nombre,
                codigo
            ),
            servicios (
                nombre
            )
        """).eq("venta_id", venta_id).execute()
        
        venta = venta_response.data[0]
        venta["detalles"] = detalle_response.data if detalle_response.data else []
        
        return venta
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener detalle de venta: {str(e)}")

@router.get("/estadisticas", response_model=VentaEstadisticas,
    dependencies=[Depends(PermissionDependency("puede_ver_ventas"))]
)
async def get_estadisticas_ventas(
    business_id: str,
    request: Request,
) -> Any:
    """
    Obtener estadísticas de ventas del negocio.
    """
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación requerido"
        )
    
    supabase = get_scoped_supabase_user_client(token, business_id)
    
    try:
        # Ventas totales
        ventas_response = supabase.table("ventas").select("total, fecha").eq("negocio_id", business_id).execute()
        ventas = ventas_response.data if ventas_response.data else []
        
        total_ventas = len(ventas)
        total_ingresos = sum(venta["total"] for venta in ventas)
        venta_promedio = total_ingresos / total_ventas if total_ventas > 0 else 0
        
        # Ventas de hoy
        hoy = date.today().isoformat()
        ventas_hoy = [v for v in ventas if v["fecha"].startswith(hoy)]
        
        ventas_hoy_count = len(ventas_hoy)
        ingresos_hoy = sum(venta["total"] for venta in ventas_hoy)
        
        return VentaEstadisticas(
            total_ventas=total_ventas,
            total_ingresos=total_ingresos,
            venta_promedio=venta_promedio,
            ventas_hoy=ventas_hoy_count,
            ingresos_hoy=ingresos_hoy
        )
        
    except Exception as e:
        print(f"Error al obtener estadísticas: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener estadísticas: {str(e)}"
        )

@router.get("/reporte",
    dependencies=[Depends(PermissionDependency("puede_ver_ventas"))]
)
async def get_reporte_ventas(
    business_id: str,
    request: Request,
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None,
) -> Any:
    """
    Obtener reporte detallado de ventas.
    """
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación requerido"
        )
    
    supabase = get_scoped_supabase_user_client(token, business_id)
    
    try:
        query = supabase.table("ventas").select("*, venta_detalle(*, productos(nombre), servicios(nombre))").eq("negocio_id", business_id)
        
        if fecha_inicio:
            query = query.gte("fecha", fecha_inicio)
        if fecha_fin:
            query = query.lte("fecha", fecha_fin)
        
        response = query.execute()
        ventas = response.data if response.data else []
        
        # Calcular resumen en niveles superiores para facilitar consumo en frontend
        total_ventas = len(ventas)
        total_ingresos = sum(float(v.get("total") or 0) for v in ventas)
        
        # Calcular productos/servicios más vendidos (opcional)
        top_items = {}
        for v in ventas:
            detalles = v.get("venta_detalle") or []
            for d in detalles:
                tipo = d.get("tipo")
                if tipo == "producto":
                    key = f'producto:{d.get("producto_id")}'
                    nombre = (d.get("productos") or {}).get("nombre") if isinstance(d.get("productos"), dict) else None
                    nombre = nombre or "Producto"
                elif tipo == "servicio":
                    key = f'servicio:{d.get("servicio_id")}'
                    nombre = (d.get("servicios") or {}).get("nombre") if isinstance(d.get("servicios"), dict) else None
                    nombre = nombre or "Servicio"
                else:
                    continue
                cantidad = int(d.get("cantidad") or 0)
                subtotal = float(d.get("subtotal") or 0)
                if subtotal == 0:
                    precio_unitario = float(d.get("precio_unitario") or 0)
                    subtotal = precio_unitario * cantidad
                if key not in top_items:
                    top_items[key] = {"nombre": nombre, "cantidad": 0, "total": 0.0}
                top_items[key]["cantidad"] += cantidad
                top_items[key]["total"] += subtotal
        
        productos_mas_vendidos = sorted(top_items.values(), key=lambda x: x["cantidad"], reverse=True)[:6]
        
        return {
            "ventas": ventas,
            "total_ventas": total_ventas,
            "total_ingresos": total_ingresos,
            "ganancias_netas": total_ingresos,
            "productos_mas_vendidos": productos_mas_vendidos,
        }
        
    except Exception as e:
        print(f"Error al obtener reporte: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener reporte: {str(e)}"
        )

@router.get("/dashboard-stats", response_model=DashboardStats)
async def get_dashboard_stats(
    authorization: str = Header(..., description="Bearer token")
):
    """
    Obtener estadísticas para el dashboard del negocio.
    """
    try:
        client = get_supabase_user_client(authorization)
        
        # Obtener el user_id del token JWT
        user_id = get_user_id_from_token(authorization)
        
        # Obtener el negocio del usuario autenticado
        usuario_negocio_response = client.table("usuarios_negocios").select("negocio_id").eq("usuario_id", user_id).eq("estado", "aceptado").execute()
        
        if not usuario_negocio_response.data:
            raise HTTPException(status_code=404, detail="No se encontró un negocio asociado al usuario")
        
        negocio_id = usuario_negocio_response.data[0]["negocio_id"]
        
        # Obtener total de productos
        productos_response = client.table("productos").select("id").eq("negocio_id", negocio_id).execute()
        total_products = len(productos_response.data) if productos_response.data else 0
        
        # Obtener total de clientes
        clientes_response = client.table("clientes").select("id").eq("negocio_id", negocio_id).execute()
        total_customers = len(clientes_response.data) if clientes_response.data else 0
        
        # Obtener total de ventas
        ventas_response = client.table("ventas").select("id, total, fecha").eq("negocio_id", negocio_id).execute()
        total_sales = len(ventas_response.data) if ventas_response.data else 0
        
        # Calcular ingresos del mes actual
        hoy = date.today()
        primer_dia_mes = date(hoy.year, hoy.month, 1)
        ultimo_dia_mes = date(hoy.year, hoy.month, calendar.monthrange(hoy.year, hoy.month)[1])
        
        ventas_mes = []
        if ventas_response.data:
            for venta in ventas_response.data:
                fecha_venta = datetime.fromisoformat(venta["fecha"].replace('Z', '+00:00')).date()
                if primer_dia_mes <= fecha_venta <= ultimo_dia_mes:
                    ventas_mes.append(venta)
        
        monthly_revenue = sum(venta["total"] for venta in ventas_mes)
        
        # Obtener productos con stock bajo (menos de 10 unidades)
        productos_stock_response = client.table("productos").select("id, stock_actual").eq("negocio_id", negocio_id).lt("stock_actual", 10).execute()
        low_stock_products = len(productos_stock_response.data) if productos_stock_response.data else 0
        
        # Obtener pedidos pendientes (por ahora retornamos 0 ya que no tenemos tabla de pedidos)
        pending_orders = 0
        
        return DashboardStats(
            totalProducts=total_products,
            totalCustomers=total_customers,
            totalSales=total_sales,
            monthlyRevenue=monthly_revenue,
            lowStockProducts=low_stock_products,
            pendingOrders=pending_orders
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener estadísticas del dashboard: {str(e)}")

@router.get("/recent-activity")
async def get_recent_activity(
    authorization: str = Header(..., description="Bearer token")
):
    """
    Obtener actividad reciente del negocio (últimas ventas, productos agregados, clientes registrados).
    """
    try:
        client = get_supabase_user_client(authorization)
        
        # Obtener el user_id del token JWT
        user_id = get_user_id_from_token(authorization)
        
        # Obtener el negocio del usuario autenticado
        usuario_negocio_response = client.table("usuarios_negocios").select("negocio_id").eq("usuario_id", user_id).eq("estado", "aceptado").execute()
        
        if not usuario_negocio_response.data:
            raise HTTPException(status_code=404, detail="No se encontró un negocio asociado al usuario")
        
        negocio_id = usuario_negocio_response.data[0]["negocio_id"]
        
        actividades = []
        
        # Obtener últimas 3 ventas
        ventas_response = client.table("ventas").select("id, total, fecha, clientes(nombre)").eq("negocio_id", negocio_id).order("fecha", desc=True).limit(3).execute()
        
        if ventas_response.data:
            for venta in ventas_response.data:
                cliente_nombre = venta.get("clientes", {}).get("nombre", "Cliente") if venta.get("clientes") else "Cliente"
                actividades.append({
                    "tipo": "venta",
                    "titulo": "Nueva venta registrada",
                    "descripcion": f"Venta por ${venta['total']:.2f} - {cliente_nombre}",
                    "fecha": venta["fecha"],
                    "icono": "shopping-cart",
                    "color": "green"
                })
        
        # Obtener últimos 2 productos agregados
        productos_response = client.table("productos").select("nombre, creado_en").eq("negocio_id", negocio_id).order("creado_en", desc=True).limit(2).execute()
        
        if productos_response.data:
            for producto in productos_response.data:
                actividades.append({
                    "tipo": "producto",
                    "titulo": "Producto agregado",
                    "descripcion": f'Nuevo producto "{producto["nombre"]}" agregado al inventario',
                    "fecha": producto["creado_en"],
                    "icono": "package",
                    "color": "blue"
                })
        
        # Obtener últimos 2 clientes registrados
        clientes_response = client.table("clientes").select("nombre, apellido, creado_en").eq("negocio_id", negocio_id).order("creado_en", desc=True).limit(2).execute()
        
        if clientes_response.data:
            for cliente in clientes_response.data:
                nombre_completo = f"{cliente['nombre']} {cliente['apellido']}"
                actividades.append({
                    "tipo": "cliente",
                    "titulo": "Nuevo cliente registrado",
                    "descripcion": f"{nombre_completo} se registró como cliente",
                    "fecha": cliente["creado_en"],
                    "icono": "users",
                    "color": "purple"
                })
        
        # Ordenar todas las actividades por fecha (más reciente primero)
        # Filtrar actividades con fecha válida y ordenar
        actividades_con_fecha = [a for a in actividades if a.get("fecha")]
        actividades_ordenadas = sorted(actividades_con_fecha, key=lambda x: x["fecha"], reverse=True)
        
        # Limitar a las 6 actividades más recientes
        actividades_recientes = actividades_ordenadas[:6]
        
        return {
            "actividades": actividades_recientes,
            "total": len(actividades_recientes)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener actividad reciente: {str(e)}")

@router.get("/monthly-sales-chart")
async def get_monthly_sales_chart(
    authorization: str = Header(..., description="Bearer token")
):
    """
    Obtener datos para el gráfico de ventas del mes actual.
    """
    try:
        client = get_supabase_user_client(authorization)
        
        # Obtener el user_id del token JWT
        user_id = get_user_id_from_token(authorization)
        
        # Obtener el negocio del usuario autenticado
        usuario_negocio_response = client.table("usuarios_negocios").select("negocio_id").eq("usuario_id", user_id).eq("estado", "aceptado").execute()
        
        if not usuario_negocio_response.data:
            raise HTTPException(status_code=404, detail="No se encontró un negocio asociado al usuario")
        
        negocio_id = usuario_negocio_response.data[0]["negocio_id"]
        
        # Obtener ventas del mes actual
        hoy = date.today()
        primer_dia_mes = date(hoy.year, hoy.month, 1)
        ultimo_dia_mes = date(hoy.year, hoy.month, calendar.monthrange(hoy.year, hoy.month)[1])
        
        # Obtener todas las ventas del negocio y filtrar por fecha
        ventas_response = client.table("ventas").select("total, fecha").eq("negocio_id", negocio_id).execute()
        
        # Agrupar ventas por día (solo del mes actual)
        ventas_por_dia = {}
        if ventas_response.data:
            for venta in ventas_response.data:
                fecha_venta = datetime.fromisoformat(venta["fecha"].replace('Z', '+00:00')).date()
                
                # Filtrar solo ventas del mes actual
                if primer_dia_mes <= fecha_venta <= ultimo_dia_mes:
                    dia_str = fecha_venta.strftime("%d")
                    
                    if dia_str not in ventas_por_dia:
                        ventas_por_dia[dia_str] = {
                            "dia": dia_str,
                            "fecha": fecha_venta.strftime("%Y-%m-%d"),
                            "ventas": 0,
                            "total": 0
                        }
                    
                    ventas_por_dia[dia_str]["ventas"] += 1
                    ventas_por_dia[dia_str]["total"] += float(venta["total"])
        
        # Convertir a lista ordenada por día
        datos_grafico = sorted(ventas_por_dia.values(), key=lambda x: x["dia"])
        
        return {
            "datos": datos_grafico,
            "mes": hoy.strftime("%B %Y"),
            "total_ventas": sum(d["ventas"] for d in datos_grafico),
            "total_ingresos": sum(d["total"] for d in datos_grafico)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener datos del gráfico de ventas: {str(e)}")

@router.get("/top-products-chart")
async def get_top_products_chart(
    authorization: str = Header(..., description="Bearer token")
):
    """
    Obtener datos para el gráfico de productos más vendidos.
    """
    try:
        client = get_supabase_user_client(authorization)
        
        # Obtener el user_id del token JWT
        user_id = get_user_id_from_token(authorization)
        
        # Obtener el negocio del usuario autenticado
        usuario_negocio_response = client.table("usuarios_negocios").select("negocio_id").eq("usuario_id", user_id).eq("estado", "aceptado").execute()
        
        if not usuario_negocio_response.data:
            raise HTTPException(status_code=404, detail="No se encontró un negocio asociado al usuario")
        
        negocio_id = usuario_negocio_response.data[0]["negocio_id"]
        
        # Obtener detalles de venta de productos del último mes
        hoy = date.today()
        hace_un_mes = hoy - timedelta(days=30)
        
        # Primero obtener todas las ventas del último mes
        ventas_response = client.table("ventas").select("id, fecha").eq("negocio_id", negocio_id).execute()
        
        # Filtrar ventas del último mes
        ventas_recientes = []
        if ventas_response.data:
            for venta in ventas_response.data:
                fecha_venta = datetime.fromisoformat(venta["fecha"].replace('Z', '+00:00')).date()
                if fecha_venta >= hace_un_mes:
                    ventas_recientes.append(venta["id"])
        
        # Si no hay ventas recientes, retornar datos vacíos
        if not ventas_recientes:
            return {
                "datos": [],
                "periodo": "Últimos 30 días",
                "total_items": 0
            }
        
        # Obtener detalles de venta para estas ventas
        detalles_response = client.table("venta_detalle").select("cantidad, producto_id, servicio_id, tipo, venta_id").in_("venta_id", ventas_recientes).execute()
        
        # Agrupar por producto/servicio
        items_vendidos = {}
        
        if detalles_response.data:
            for detalle in detalles_response.data:
                if detalle["tipo"] == "producto" and detalle.get("producto_id"):
                    # Obtener nombre del producto
                    producto_response = client.table("productos").select("nombre").eq("id", detalle["producto_id"]).execute()
                    if producto_response.data:
                        nombre = producto_response.data[0]["nombre"]
                        item_id = detalle["producto_id"]
                    else:
                        continue
                elif detalle["tipo"] == "servicio" and detalle.get("servicio_id"):
                    # Obtener nombre del servicio
                    servicio_response = client.table("servicios").select("nombre").eq("id", detalle["servicio_id"]).execute()
                    if servicio_response.data:
                        nombre = servicio_response.data[0]["nombre"]
                        item_id = detalle["servicio_id"]
                    else:
                        continue
                else:
                    continue
                
                if item_id not in items_vendidos:
                    items_vendidos[item_id] = {
                        "nombre": nombre,
                        "tipo": detalle["tipo"],
                        "cantidad_total": 0
                    }
                
                items_vendidos[item_id]["cantidad_total"] += int(detalle["cantidad"])
        
        # Ordenar por cantidad vendida y tomar los top 5
        top_items = sorted(items_vendidos.values(), key=lambda x: x["cantidad_total"], reverse=True)[:5]
        
        return {
            "datos": top_items,
            "periodo": "Últimos 30 días",
            "total_items": len(items_vendidos)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener datos del gráfico de productos: {str(e)}") 

@router.get("/dashboard-stats-v2", response_model=DashboardStatsResponse)
async def get_dashboard_stats_v2(
    authorization: str = Header(..., description="Bearer token"),
    negocio_id: Optional[str] = None
):
    """
    Obtiene estadísticas del dashboard incluyendo ventas, ganancias y clientes nuevos
    para diferentes períodos de tiempo. Optimizado para reducir consultas a la base de datos.
    """
    start_time = time.time()
    try:
        client = get_supabase_user_client(authorization)
        
        if not negocio_id:
            raise HTTPException(status_code=400, detail="negocio_id es requerido")
        
        print(f"[DASHBOARD] Iniciando dashboard-stats-v2 para negocio {negocio_id}")

        # Obtener fechas de inicio para cada período
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        
        # Inicio de la semana (lunes)
        week_start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        
        # Inicio del mes
        month_start = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ).isoformat()

        # OPTIMIZACIÓN: Obtener todas las ventas del mes de una vez (incluye today y week)
        query_start = time.time()
        try:
            ventas_mes = client.table("ventas") \
                .select("id, total, fecha") \
                .eq("negocio_id", negocio_id) \
                .gte("fecha", month_start) \
                .execute()
            
            ventas_data = ventas_mes.data if ventas_mes.data else []
            print(f"[DASHBOARD] Consulta ventas: {len(ventas_data)} registros en {time.time() - query_start:.2f}s")
        except Exception as e:
            print(f"[DASHBOARD] Error obteniendo ventas: {str(e)}")
            ventas_data = []

        # OPTIMIZACIÓN: Obtener todos los detalles de ventas del mes de una vez
        query_start = time.time()
        try:
            if ventas_data:
                venta_ids = [v["id"] for v in ventas_data]
                detalles_mes = client.table("venta_detalle") \
                    .select("venta_id, producto_id, servicio_id, cantidad, precio_unitario, subtotal") \
                    .in_("venta_id", venta_ids) \
                    .execute()
                
                detalles_data = detalles_mes.data if detalles_mes.data else []
                print(f"[DASHBOARD] Consulta detalles: {len(detalles_data)} registros en {time.time() - query_start:.2f}s")
            else:
                detalles_data = []
                print(f"[DASHBOARD] Sin ventas, saltando detalles")
        except Exception as e:
            print(f"[DASHBOARD] Error obteniendo detalles: {str(e)}")
            detalles_data = []

        # OPTIMIZACIÓN: Obtener todos los productos y servicios de una vez
        try:
            # Obtener IDs únicos de productos y servicios
            producto_ids = list(set(d["producto_id"] for d in detalles_data if d.get("producto_id")))
            servicio_ids = list(set(d["servicio_id"] for d in detalles_data if d.get("servicio_id")))
            
            # Obtener productos con nombres y costos
            productos_info = {}
            if producto_ids:
                productos_response = client.table("productos") \
                    .select("id, nombre, precio_compra") \
                    .in_("id", producto_ids) \
                    .execute()
                
                if productos_response.data:
                    productos_info = {
                        p["id"]: {
                            "nombre": p.get("nombre", "Producto sin nombre"),
                            "costo": p.get("precio_compra", 0) or 0
                        }
                        for p in productos_response.data
                    }
            
            # Obtener servicios con nombres y costos
            servicios_info = {}
            if servicio_ids:
                servicios_response = client.table("servicios") \
                    .select("id, nombre, costo") \
                    .in_("id", servicio_ids) \
                    .execute()
                
                if servicios_response.data:
                    servicios_info = {
                        s["id"]: {
                            "nombre": s.get("nombre", "Servicio sin nombre"),
                            "costo": s.get("costo", 0) or 0
                        }
                        for s in servicios_response.data
                    }
        except Exception as e:
            print(f"Error obteniendo productos/servicios: {str(e)}")
            productos_info = {}
            servicios_info = {}

        # OPTIMIZACIÓN: Obtener datos de clientes y productos de forma secuencial para evitar problemas
        try:
            # Consultas individuales para evitar problemas de concurrencia
            clientes_mes = client.table("clientes") \
                .select("id, creado_en") \
                .eq("negocio_id", negocio_id) \
                .gte("creado_en", month_start) \
                .execute()
            
            total_clientes_response = client.table("clientes") \
                .select("id") \
                .eq("negocio_id", negocio_id) \
                .execute()
            
            total_productos_response = client.table("productos") \
                .select("id") \
                .eq("negocio_id", negocio_id) \
                .execute()
            
            productos_stock_bajo_response = client.table("productos") \
                .select("id") \
                .eq("negocio_id", negocio_id) \
                .lt("stock_actual", 10) \
                .execute()
            
            # Procesar resultados
            clientes_data = clientes_mes.data if clientes_mes.data else []
            total_customers = len(total_clientes_response.data) if total_clientes_response.data else 0
            total_products = len(total_productos_response.data) if total_productos_response.data else 0
            low_stock_products = len(productos_stock_bajo_response.data) if productos_stock_bajo_response.data else 0
            
            print(f"[DASHBOARD] Conteos obtenidos - Productos: {total_products}, Clientes: {total_customers}, Stock bajo: {low_stock_products}")
            
        except Exception as e:
            print(f"Error obteniendo datos adicionales: {str(e)}")
            clientes_data = []
            total_customers = 0
            total_products = 0
            low_stock_products = 0

        # Función auxiliar optimizada para calcular estadísticas
        def calculate_period_stats(start_date: str) -> DashboardStatsPeriod:
            try:
                # Filtrar ventas del período
                ventas_periodo = [v for v in ventas_data if v.get("fecha", "") >= start_date]
                
                if not ventas_periodo:
                    return DashboardStatsPeriod(
                        total_sales=0.0,
                        estimated_profit=0.0,
                        new_customers=0
                    )
                
                # Calcular total de ventas
                total_sales = sum(float(v.get("total", 0) or 0) for v in ventas_periodo)
                
                # Calcular ganancias estimadas
                venta_ids_periodo = [v["id"] for v in ventas_periodo]
                detalles_periodo = [d for d in detalles_data if d.get("venta_id") in venta_ids_periodo]
                
                ganancia = 0.0
                for detalle in detalles_periodo:
                    try:
                        cantidad = float(detalle.get("cantidad", 0) or 0)
                        precio_unitario = float(detalle.get("precio_unitario", 0) or 0)
                        
                        if detalle.get("producto_id"):
                            producto_info = productos_info.get(detalle["producto_id"], {})
                            costo = float(producto_info.get("costo", 0) or 0)
                            ganancia += (precio_unitario - costo) * cantidad
                        elif detalle.get("servicio_id"):
                            servicio_info = servicios_info.get(detalle["servicio_id"], {})
                            costo = float(servicio_info.get("costo", 0) or 0)
                            ganancia += (precio_unitario - costo) * cantidad
                    except (TypeError, ValueError, AttributeError):
                        continue
                
                # Contar clientes nuevos del período
                clientes_periodo = [c for c in clientes_data if c.get("creado_en", "") >= start_date]
                new_customers = len(clientes_periodo)
                
                return DashboardStatsPeriod(
                    total_sales=round(total_sales, 2),
                    estimated_profit=round(max(0.0, ganancia), 2),
                    new_customers=new_customers
                )
            
            except Exception as e:
                print(f"Error calculando estadísticas para {start_date}: {str(e)}")
                return DashboardStatsPeriod(
                    total_sales=0.0,
                    estimated_profit=0.0,
                    new_customers=0
                )

        # Calcular estadísticas para cada período
        today_stats = calculate_period_stats(today_start)
        week_stats = calculate_period_stats(week_start)
        month_stats = calculate_period_stats(month_start)

        # Calcular top items vendidos del mes
        top_items = []
        try:
            # Procesar productos y servicios vendidos
            productos_vendidos = {}
            servicios_vendidos = {}
            
            for detalle in detalles_data:
                try:
                    cantidad = int(detalle.get("cantidad", 0) or 0)
                    subtotal = float(detalle.get("subtotal", 0) or 0)
                    
                    if detalle.get("producto_id"):
                        prod_id = detalle["producto_id"]
                        if prod_id not in productos_vendidos:
                            productos_vendidos[prod_id] = {
                                "cantidad_total": 0,
                                "ingreso_total": 0.0
                            }
                        productos_vendidos[prod_id]["cantidad_total"] += cantidad
                        productos_vendidos[prod_id]["ingreso_total"] += subtotal
                    
                    elif detalle.get("servicio_id"):
                        serv_id = detalle["servicio_id"]
                        if serv_id not in servicios_vendidos:
                            servicios_vendidos[serv_id] = {
                                "cantidad_total": 0,
                                "ingreso_total": 0.0
                            }
                        servicios_vendidos[serv_id]["cantidad_total"] += cantidad
                        servicios_vendidos[serv_id]["ingreso_total"] += subtotal
                except (TypeError, ValueError, AttributeError):
                    continue
            
            # Agregar productos a top_items
            for prod_id, data in productos_vendidos.items():
                producto_info = productos_info.get(prod_id, {})
                top_items.append({
                    "nombre": str(producto_info.get("nombre", "Producto sin nombre")),
                    "tipo": "Producto",
                    "cantidad_total": int(data.get("cantidad_total", 0)),
                    "ingreso_total": round(float(data.get("ingreso_total", 0)), 2)
                })
            
            # Agregar servicios a top_items
            for serv_id, data in servicios_vendidos.items():
                servicio_info = servicios_info.get(serv_id, {})
                top_items.append({
                    "nombre": str(servicio_info.get("nombre", "Servicio sin nombre")),
                    "tipo": "Servicio",
                    "cantidad_total": int(data.get("cantidad_total", 0)),
                    "ingreso_total": round(float(data.get("ingreso_total", 0)), 2)
                })
            
            # Ordenar por cantidad vendida y tomar los primeros 5
            top_items.sort(key=lambda x: x.get("cantidad_total", 0), reverse=True)
            top_items = top_items[:5]
        
        except Exception as e:
            print(f"Error procesando top items: {str(e)}")
            top_items = []

        total_time = time.time() - start_time
        print(f"[DASHBOARD] Completado en {total_time:.2f}s")
        
        # Asegurar que todos los valores sean serializables
        response_data = DashboardStatsResponse(
            today=today_stats,
            week=week_stats,
            month=month_stats,
            top_items=top_items,
            total_products=int(total_products),
            total_customers=int(total_customers),
            low_stock_products=int(low_stock_products)
        )
        
        return response_data

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        total_time = time.time() - start_time
        print(f"[DASHBOARD] Error después de {total_time:.2f}s: {str(e)}")
        import traceback
        print(f"[DASHBOARD] Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/dashboard-stats/window", response_model=DashboardSalesWindowResponse)
async def get_dashboard_sales_window(
    authorization: str = Header(..., description="Bearer token"),
    negocio_id: str = Query(..., description="Identificador del negocio"),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=180),
    since: Optional[date] = Query(None),
    until: Optional[date] = Query(None),
):
    """
    Devuelve las filas agregadas del dashboard desde la vista/materialized view `mv_dashboard_sales_daily`
    con paginación basada en limit/offset. Usar este endpoint para dashboards que requieren streaming
    de datos por bloques sin recalcular métricas en cada request.
    """
    client = get_supabase_user_client(authorization)

    today = datetime.utcnow().date()
    default_since = today - timedelta(days=90)
    since = since or default_since
    until = until or today

    safe_page = max(page, 1)
    safe_page_size = max(1, min(page_size, 180))
    offset = (safe_page - 1) * safe_page_size

    params = {
        "p_negocio_id": negocio_id,
        "p_since": since.isoformat(),
        "p_until": until.isoformat(),
        "p_limit": safe_page_size,
        "p_offset": offset,
    }

    try:
        rpc_response = client.rpc("dashboard_sales_window", params).execute()
        window_rows = rpc_response.data or []
    except Exception as exc:
        logger.warning("dashboard_sales_window RPC fallo para negocio %s: %s", negocio_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo obtener la agregación de ventas",
        ) from exc

    def _parse_date(value: Any) -> date:
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value).date()
            except ValueError:
                try:
                    return datetime.strptime(value.split("T")[0], "%Y-%m-%d").date()
                except ValueError:
                    return today
        return today

    rows = [
        DashboardSalesWindowRow(
            date=_parse_date(item.get("dia")),
            total=float(item.get("total", item.get("total_bruto", 0)) or 0),
            cost=float(item.get("costo", item.get("costo_total", 0)) or 0),
            profit=float(item.get("ganancia", 0) or 0),
            customers=int(item.get("clientes", item.get("clientes_unicos", 0)) or 0),
            orders=int(item.get("total_ventas", item.get("orders", 0)) or 0),
        )
        for item in window_rows
    ]

    next_cursor = None
    if len(rows) == safe_page_size:
        next_cursor = str(safe_page + 1)

    return DashboardSalesWindowResponse(
        rows=rows,
        next_cursor=next_cursor,
        page=safe_page,
        page_size=safe_page_size,
    )

@router.get("/sales", response_model=List[dict])
async def get_recent_sales(
    authorization: str = Header(..., description="Bearer token")
):
    """
    Obtiene las ventas más recientes para ser mostradas en el dashboard.
    Este endpoint es utilizado por la función getRecentSales() del frontend.
    No requiere business_id ya que debe obtener ventas de todos los negocios a los que tiene acceso el usuario.
    
    Returns:
        List[dict]: Lista de ventas recientes con formato simplificado para el dashboard
    """
    try:
        # Extraemos el usuario del token
        user_id = get_user_id_from_token(authorization)
        
        # Obtenemos el cliente Supabase
        supabase = get_supabase_user_client(authorization)
        
        # Consultamos los IDs de los negocios a los que tiene acceso el usuario
        negocios_response = supabase.table("usuarios_negocios").select("negocio_id").eq("usuario_id", user_id).execute()
        
        if not negocios_response.data:
            return []
        
        # Extraemos los IDs de negocios
        negocio_ids = [item["negocio_id"] for item in negocios_response.data]
        
        # Obtenemos las ventas más recientes de esos negocios
        ventas_response = supabase.table("ventas")\
            .select("*, clientes(nombre, apellido)")\
            .in_("negocio_id", negocio_ids)\
            .order("fecha", desc=True)\
            .limit(10)\
            .execute()
            
        # Formateamos los resultados
        formatted_sales = []
        for venta in ventas_response.data:
            cliente_nombre = "Cliente no registrado"
            if venta.get("clientes") and venta["clientes"]:
                nombre_completo = f"{venta['clientes']['nombre'] or ''} {venta['clientes']['apellido'] or ''}".strip()
                cliente_nombre = nombre_completo if nombre_completo else "Cliente no registrado"
                
            formatted_sales.append({
                "id": venta["id"],
                "fecha": venta["fecha"],
                "total": float(venta["total"]) if "total" in venta else 0.0,
                "negocio_id": venta["negocio_id"],
                "cliente_nombre": cliente_nombre,
                "metodo_pago": venta.get("medio_pago", "")
            })
            
        return formatted_sales
        
    except Exception as e:
        print(f"Error en get_recent_sales: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener ventas recientes: {str(e)}"
        )

@router.get("/health-check")
async def health_check(
    authorization: str = Header(..., description="Bearer token"),
    negocio_id: Optional[str] = None
):
    """
    Endpoint simple para verificar conectividad básica con la base de datos.
    """
    start_time = time.time()
    try:
        client = get_supabase_user_client(authorization)
        
        if not negocio_id:
            raise HTTPException(status_code=400, detail="negocio_id es requerido")
        
        print(f"[HEALTH] Iniciando health check para negocio {negocio_id}")
        
        # Consulta simple: contar ventas
        query_start = time.time()
        ventas_count = client.table("ventas") \
            .select("id") \
            .eq("negocio_id", negocio_id) \
            .execute()
        
        query_time = time.time() - query_start
        print(f"[HEALTH] Consulta ventas completada en {query_time:.2f}s")
        
        # Consulta simple: contar productos
        query_start = time.time()
        productos_count = client.table("productos") \
            .select("id") \
            .eq("negocio_id", negocio_id) \
            .execute()
        
        query_time = time.time() - query_start
        print(f"[HEALTH] Consulta productos completada en {query_time:.2f}s")
        
        total_time = time.time() - start_time
        print(f"[HEALTH] Health check completado en {total_time:.2f}s")
        
        return {
            "status": "ok",
            "negocio_id": negocio_id,
            "ventas_count": ventas_count.count if ventas_count.count is not None else 0,
            "productos_count": productos_count.count if productos_count.count is not None else 0,
            "response_time": f"{total_time:.2f}s"
        }
        
    except Exception as e:
        total_time = time.time() - start_time
        print(f"[HEALTH] Error después de {total_time:.2f}s: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error en health check: {str(e)}") 
