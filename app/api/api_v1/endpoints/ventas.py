from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from datetime import datetime, date, timedelta
import calendar
from pydantic import BaseModel, Field
import uuid
import jwt
import json
import time
import asyncio

from app.db.supabase_client import get_supabase_client, get_supabase_user_client
from app.dependencies import verify_permission, PermissionDependency

router = APIRouter()

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
    items: List[VentaItemCreate] = Field(..., min_items=1, description="Debe incluir al menos un item")
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
    cliente_id: str
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

@router.post("/record-sale", response_model=VentaResponseSimple)
async def record_sale(
    venta_data: VentaRequest,
    authorization: str = Header(..., description="Bearer token")
):
    """
    Registra una nueva venta y actualiza el stock de productos.
    """
    try:
        # Obtener cliente autenticado
        client = get_supabase_user_client(authorization)
        
        # Obtener el user_id del usuario autenticado
        user_id = get_user_id_from_token(authorization)
        
        # Obtener el usuario_negocio_id del usuario autenticado
        # Por ahora usamos un negocio conocido para testing
        negocio_id = "de138c82-abaa-4f3b-86de-1c98edbef33b"
        
        usuario_negocio_response = client.table("usuarios_negocios").select("id").eq("usuario_id", user_id).eq("negocio_id", negocio_id).execute()
        
        if not usuario_negocio_response.data:
            raise HTTPException(status_code=403, detail=f"Usuario no tiene acceso al negocio {negocio_id}")
        
        usuario_negocio_id = usuario_negocio_response.data[0]["id"]
        
        # Validar que el cliente existe y pertenece al negocio
        cliente_response = client.table("clientes").select("id").eq("id", venta_data.cliente_id).eq("negocio_id", negocio_id).execute()
        
        if not cliente_response.data:
            raise HTTPException(status_code=404, detail=f"Cliente {venta_data.cliente_id} no encontrado o no pertenece al negocio {negocio_id}")
        
        # Calcular total y validar stock
        total = 0.0
        items_validados = []
        
        for item in venta_data.items:
            if item.tipo == "producto":
                # Verificar que el producto existe y tiene stock suficiente
                producto_response = client.table("productos").select("id, nombre, precio_venta, stock_actual").eq("id", item.id).eq("negocio_id", negocio_id).execute()
                
                if not producto_response.data:
                    raise HTTPException(status_code=404, detail=f"Producto {item.id} no encontrado")
                
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
                    raise HTTPException(status_code=404, detail=f"Servicio {item.id} no encontrado")
                
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
            "cliente_id": venta_data.cliente_id,
            "usuario_negocio_id": usuario_negocio_id,  # Agregar el usuario_negocio_id
            "total": total,
            "medio_pago": venta_data.metodo_pago,  # Mapear metodo_pago a medio_pago
            "fecha": datetime.now().isoformat(),
            "observaciones": venta_data.observaciones
        }
        
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
                producto_response = client.table("productos").select("stock_actual").eq("id", item.id).execute()
                if producto_response.data:
                    stock_actual = producto_response.data[0]["stock_actual"]
                    nuevo_stock = stock_actual - item.cantidad
                    
                    # Reducir stock
                    client.table("productos").update({
                        "stock_actual": nuevo_stock
                    }).eq("id", item.id).execute()
        
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
    authorization: str = Header(..., description="Bearer token")
):
    """
    Obtiene todas las ventas del negocio del usuario autenticado.
    """
    try:
        client = get_supabase_user_client(authorization)
        
        # Por ahora usamos un negocio conocido para testing
        negocio_id = "de138c82-abaa-4f3b-86de-1c98edbef33b"
        
        # Obtener ventas con información del cliente
        ventas_response = client.table("ventas").select("""
            id,
            fecha,
            total,
            medio_pago,
            estado,
            observaciones,
            clientes (
                nombre,
                email
            )
        """).eq("negocio_id", negocio_id).order("fecha", desc=True).execute()
        
        return {
            "ventas": ventas_response.data if ventas_response.data else [],
            "total_ventas": len(ventas_response.data) if ventas_response.data else 0
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener ventas: {str(e)}")

@router.get("/sales/{venta_id}")
async def get_sale_detail(
    venta_id: str,
    authorization: str = Header(..., description="Bearer token")
):
    """
    Obtiene el detalle de una venta específica.
    """
    try:
        client = get_supabase_user_client(authorization)
        
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
    
    supabase = get_supabase_user_client(token)
    
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
    
    supabase = get_supabase_user_client(token)
    
    try:
        query = supabase.table("ventas").select("*, venta_detalle(*, productos(nombre))").eq("negocio_id", business_id)
        
        if fecha_inicio:
            query = query.gte("fecha", fecha_inicio)
        if fecha_fin:
            query = query.lte("fecha", fecha_fin)
        
        response = query.execute()
        return {
            "ventas": response.data if response.data else [],
            "resumen": {
                "total_ventas": len(response.data) if response.data else 0,
                "total_ingresos": sum(v["total"] for v in response.data) if response.data else 0
            }
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
    negocio_id: str = None
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

@router.get("/health-check")
async def health_check(
    authorization: str = Header(..., description="Bearer token"),
    negocio_id: str = None
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
            .select("id", count="exact") \
            .eq("negocio_id", negocio_id) \
            .execute()
        
        query_time = time.time() - query_start
        print(f"[HEALTH] Consulta ventas completada en {query_time:.2f}s")
        
        # Consulta simple: contar productos
        query_start = time.time()
        productos_count = client.table("productos") \
            .select("id", count="exact") \
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