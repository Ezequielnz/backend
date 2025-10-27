from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query, Response
from fastapi.responses import JSONResponse
from datetime import datetime, date, timedelta
from decimal import Decimal
import calendar
import json
from dateutil.relativedelta import relativedelta

from app.types.auth import User
from app.api.deps import get_current_user_from_request as get_current_user
from app.api.context import BusinessScopedClientDep, ScopedClientContext
from app.schemas.finanzas import (
    CategoriaFinancieraCreate, CategoriaFinancieraUpdate, CategoriaFinanciera,
    MovimientoFinancieroCreate, MovimientoFinancieroUpdate, MovimientoFinanciero, MovimientoFinancieroConCategoria,
    CuentaPendienteCreate, CuentaPendienteUpdate, CuentaPendiente, CuentaPendienteConCliente,
    ResumenFinanciero, FlujoCajaMensual, FlujoCajaDiario
)
from app.dependencies import PermissionDependency
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Helper function para serializar datos para JSON
def serialize_for_json(data):
    """Convert Python objects to JSON-serializable types."""
    if data is None:
        return None
    elif isinstance(data, Decimal):
        return float(data)
    elif isinstance(data, datetime):
        return data.isoformat()  # Full ISO format with T separator
    elif isinstance(data, date):
        return data.strftime('%Y-%m-%d')  # Date-only format
    elif isinstance(data, dict):
        return {k: serialize_for_json(v) for k, v in data.items()}
    elif isinstance(data, (list, tuple)):
        return [serialize_for_json(item) for item in data]
    elif hasattr(data, 'dict') and callable(getattr(data, 'dict')):
        # Para objetos Pydantic
        return serialize_for_json(data.dict())
    elif isinstance(data, (str, int, float, bool)):
        return data
    else:
        # Para cualquier otro tipo, intentar convertir a string
        try:
            return str(data)
        except Exception:
            return None

# ============================================================================
# CATEGORIAS FINANCIERAS
# ============================================================================

@router.get("/categorias", response_model=List[CategoriaFinanciera],
    dependencies=[Depends(PermissionDependency("facturacion", "ver"))]
)
async def get_categorias_financieras(
    business_id: str,
    tipo: Optional[str] = Query(None, regex="^(ingreso|egreso)$"),
    activo: Optional[bool] = Query(True),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """Get financial categories for a business."""
    supabase = scoped.client
    
    try:
        query = supabase.table("categorias_financieras").select("*").eq("negocio_id", business_id)
        
        if tipo:
            query = query.eq("tipo", tipo)
        if activo is not None:
            query = query.eq("activo", activo)
            
        response = query.order("nombre").execute()
        return JSONResponse(status_code=200, content=response.data if response.data else [])
        
    except Exception as e:
        logger.error(f"Error fetching financial categories: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener las categorías financieras"
        )

@router.post("/categorias", response_model=CategoriaFinanciera,
    dependencies=[Depends(PermissionDependency("facturacion", "editar"))]
)
async def create_categoria_financiera(
    business_id: str,
    categoria_in: CategoriaFinancieraCreate,
    current_user: User = Depends(get_current_user),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """Create a new financial category."""
    supabase = scoped.client
    
    try:
        # Check if category already exists
        existing = supabase.table("categorias_financieras").select("id").eq("negocio_id", business_id).eq("nombre", categoria_in.nombre).eq("tipo", categoria_in.tipo).execute()
        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe una categoría con este nombre y tipo"
            )
        
        categoria_data = categoria_in.dict()
        categoria_data["negocio_id"] = business_id
        categoria_data["creado_por"] = current_user.id
        
        response = supabase.table("categorias_financieras").insert(categoria_data).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al crear la categoría financiera"
            )
            
        return response.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating financial category: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear la categoría financiera"
        )

@router.put("/categorias/{categoria_id}", response_model=CategoriaFinanciera,
    dependencies=[Depends(PermissionDependency("facturacion", "editar"))]
)
async def update_categoria_financiera(business_id: str,
    categoria_id: str,
    categoria_update: CategoriaFinancieraUpdate, scoped: ScopedClientContext = Depends(BusinessScopedClientDep)) -> Any:
    """Update a financial category."""
    supabase = scoped.client
    
    try:
        # Verify category exists and belongs to business
        existing = supabase.table("categorias_financieras").select("*").eq("id", categoria_id).eq("negocio_id", business_id).execute()
        if not existing.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoría financiera no encontrada"
            )
        
        update_data = categoria_update.dict(exclude_unset=True)
        if not update_data:
            return existing.data[0]
        
        response = (
            supabase
            .table("categorias_financieras")
            .update(update_data)
            .eq("id", categoria_id)
            .eq("negocio_id", business_id)
            .execute()
        )
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al actualizar la categoría financiera"
            )
            
        return response.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating financial category: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar la categoría financiera"
        )

@router.delete("/categorias/{categoria_id}",
    dependencies=[Depends(PermissionDependency("facturacion", "editar"))]
)
async def delete_categoria_financiera(business_id: str,
    categoria_id: str, scoped: ScopedClientContext = Depends(BusinessScopedClientDep)) -> Any:
    """Delete a financial category."""
    supabase = scoped.client
    
    try:
        # Verify category exists and belongs to business
        existing = supabase.table("categorias_financieras").select("id").eq("id", categoria_id).eq("negocio_id", business_id).execute()
        if not existing.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoría financiera no encontrada"
            )
        
        # Check if category is being used
        movements = supabase.table("movimientos_financieros").select("id").eq("categoria_id", categoria_id).limit(1).execute()
        if movements.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se puede eliminar la categoría porque tiene movimientos asociados"
            )
        
        response = (
            supabase
            .table("categorias_financieras")
            .delete()
            .eq("id", categoria_id)
            .eq("negocio_id", business_id)
            .execute()
        )
        
        return {"message": "Categoría financiera eliminada exitosamente"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting financial category: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar la categoría financiera"
        )

# ============================================================================
# MOVIMIENTOS FINANCIEROS
# ============================================================================

@router.get("/movimientos", response_model=List[MovimientoFinancieroConCategoria],
    dependencies=[Depends(PermissionDependency("facturacion", "ver"))]
)
async def get_movimientos_financieros(
    business_id: str,
    tipo: Optional[str] = Query(None, regex="^(ingreso|egreso)$"),
    categoria_id: Optional[str] = Query(None),
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """Get financial movements for a business with filters."""
    supabase = scoped.client
    
    try:
        # Base query for manual financial movements
        query_movimientos = supabase.table("movimientos_financieros").select("""
            *,
            categorias_financieras!inner(nombre),
            clientes(nombre, apellido)
        """).eq("negocio_id", business_id)
        
        # Apply filters to manual movements
        if tipo and tipo != "ingreso":  # Solo aplicar filtro si no es ingreso (para incluir ventas)
            query_movimientos = query_movimientos.eq("tipo", tipo)
        if categoria_id:
            query_movimientos = query_movimientos.eq("categoria_id", categoria_id)
        if fecha_desde:
            query_movimientos = query_movimientos.gte("fecha", fecha_desde.isoformat())
        if fecha_hasta:
            query_movimientos = query_movimientos.lte("fecha", fecha_hasta.isoformat())
        
        # Get manual movements
        response_movimientos = query_movimientos.order("fecha", desc=True).execute()
        
        # Query sales (ventas) if we want ingresos or no type filter
        ventas_data = []
        if not tipo or tipo == "ingreso":
            query_ventas = supabase.table("ventas").select("""
                id, total, fecha, observaciones,
                clientes(nombre, apellido)
            """).eq("negocio_id", business_id)
            
            # Apply date filters to sales
            if fecha_desde:
                query_ventas = query_ventas.gte("fecha", fecha_desde.isoformat())
            if fecha_hasta:
                query_ventas = query_ventas.lte("fecha", fecha_hasta.isoformat())
            
            response_ventas = query_ventas.order("fecha", desc=True).execute()
            ventas_data = response_ventas.data if response_ventas.data else []
        
        # Transform manual movements
        movements = []
        for item in response_movimientos.data if response_movimientos.data else []:
            # Create a copy of the item to modify safely
            item_copy = dict(item)
            
            # Convert Decimal to float for JSON serialization
            if isinstance(item_copy.get('monto'), Decimal):
                item_copy['monto'] = float(item_copy['monto'])
            
            # Ensure fecha is in string format
            if isinstance(item_copy.get('fecha'), str):
                fecha_str = item_copy['fecha']
                if 'T' in fecha_str:  # If it's a datetime string, extract date part
                    item_copy['fecha'] = fecha_str.split('T')[0]
            elif isinstance(item_copy.get('fecha'), date):
                item_copy['fecha'] = item_copy['fecha'].strftime('%Y-%m-%d')
            
            # Ensure creado_en and actualizado_en are in ISO format with T separator
            for field in ['creado_en', 'actualizado_en']:
                if isinstance(item_copy.get(field), str) and 'T' not in item_copy.get(field, ''):
                    # Si es una fecha simple YYYY-MM-DD, convertir a formato ISO 8601
                    fecha_value = item_copy.get(field)
                    if fecha_value and len(fecha_value) == 10:  # YYYY-MM-DD
                        item_copy[field] = f"{fecha_value}T00:00:00"
                elif isinstance(item_copy.get(field), date) and not isinstance(item_copy.get(field), datetime):
                    # Si es un objeto date pero no datetime, convertir a ISO
                    item_copy[field] = f"{item_copy[field].strftime('%Y-%m-%d')}T00:00:00"
            
            movement = MovimientoFinancieroConCategoria(**item_copy)
            movement.categoria_nombre = item.get("categorias_financieras", {}).get("nombre")
            if item.get("clientes"):
                client = item["clientes"]
                movement.cliente_nombre = f"{client.get('nombre', '')} {client.get('apellido', '')}" .strip()
            movements.append(movement)
        
        # Transform sales into movement format
        for venta in ventas_data:
            # Convert Decimal to float for JSON serialization
            monto_value = float(venta["total"]) if isinstance(venta["total"], Decimal) else venta["total"]
            
            # Convert timestamp to date string for fecha field
            fecha_value = venta["fecha"]
            if isinstance(fecha_value, str):
                # Handle string date/datetime
                if 'T' in fecha_value:
                    # Extract date part from timestamp string (keep as string)
                    fecha_value = fecha_value.split('T')[0]
                # fecha_value is already a string in YYYY-MM-DD format
            elif hasattr(fecha_value, 'strftime'):
                # Convert datetime/date to string
                fecha_value = fecha_value.strftime('%Y-%m-%d')
            
            # Create a movement-like object for each sale
            # Convertir fecha_value a datetime ISO completo para los campos datetime
            fecha_iso_format = None
            if isinstance(venta.get("creado_en"), datetime):
                fecha_iso_format = venta.get("creado_en").isoformat()
            elif isinstance(venta.get("fecha"), datetime):
                fecha_iso_format = venta.get("fecha").isoformat()
            else:
                # Si no hay datetime disponible, crear uno a partir de la fecha
                if isinstance(fecha_value, str) and len(fecha_value) == 10:  # YYYY-MM-DD
                    fecha_iso_format = f"{fecha_value}T00:00:00"
                else:
                    # Último recurso: fecha actual en formato ISO
                    fecha_iso_format = datetime.now().isoformat()
                    
            movement_dict = {
                "id": f"venta_{venta['id']}",  # Prefix to distinguish from manual movements
                "negocio_id": business_id,
                "tipo": "ingreso",
                "categoria_id": None,
                "monto": monto_value,
                "fecha": fecha_value,
                "metodo_pago": "venta",
                "descripcion": f"Venta #{venta['id'][:8]}...",
                "observaciones": venta.get("observaciones", ""),
                "cliente_id": None,
                "venta_id": venta["id"],
                "creado_en": fecha_iso_format,  # Ahora usa formato ISO 8601 completo
                "actualizado_en": fecha_iso_format,  # Ahora usa formato ISO 8601 completo
                "creado_por": None
            }
            
            movement = MovimientoFinancieroConCategoria(**movement_dict)
            movement.categoria_nombre = "Ventas"  # Categoría virtual para ventas
            
            if venta.get("clientes"):
                client = venta["clientes"]
                movement.cliente_nombre = f"{client.get('nombre', '')} {client.get('apellido', '')}".strip()
            
            movements.append(movement)
        
        # Sort all movements by date (desc) and apply pagination
        movements.sort(key=lambda x: x.fecha, reverse=True)
        paginated_movements = movements[offset:offset + limit]
        
        return JSONResponse(status_code=200, content=[serialize_for_json(m.dict()) for m in paginated_movements])
        
    except Exception as e:
        logger.error(f"Error fetching financial movements: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener los movimientos financieros"
        )

@router.post("/movimientos", response_model=MovimientoFinanciero,
    dependencies=[Depends(PermissionDependency("facturacion", "editar"))]
)
async def create_movimiento_financiero(
    business_id: str,
    movimiento_in: MovimientoFinancieroCreate,
    current_user: User = Depends(get_current_user),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """Create a new financial movement."""
    supabase = scoped.client
    
    try:
        # Validate category belongs to business if provided
        if movimiento_in.categoria_id:
            categoria = supabase.table("categorias_financieras").select("tipo").eq("id", movimiento_in.categoria_id).eq("negocio_id", business_id).execute()
            if not categoria.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Categoría no encontrada o no pertenece a este negocio"
                )
            
            # Validate category type matches movement type
            if categoria.data[0]["tipo"] != movimiento_in.tipo:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El tipo de categoría no coincide con el tipo de movimiento"
                )
        
        # Validate client belongs to business if provided
        if movimiento_in.cliente_id:
            cliente = supabase.table("clientes").select("id").eq("id", movimiento_in.cliente_id).eq("negocio_id", business_id).execute()
            if not cliente.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cliente no encontrado o no pertenece a este negocio"
                )
        
        movimiento_data = movimiento_in.dict()
        movimiento_data["negocio_id"] = business_id
        movimiento_data["creado_por"] = current_user.id
        
        # Convert Decimal to float and date to string for JSON serialization
        if isinstance(movimiento_data.get('monto'), Decimal):
            movimiento_data['monto'] = float(movimiento_data['monto'])
        
        if isinstance(movimiento_data.get('fecha'), date):
            movimiento_data['fecha'] = movimiento_data['fecha'].strftime('%Y-%m-%d')
        elif isinstance(movimiento_data.get('fecha'), datetime):
            movimiento_data['fecha'] = movimiento_data['fecha'].strftime('%Y-%m-%d')
        
        response = supabase.table("movimientos_financieros").insert(movimiento_data).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al crear el movimiento financiero"
            )
        
        # Convert Decimal to float and date to string in response data for JSON serialization
        result = response.data[0]
        if isinstance(result.get('monto'), Decimal):
            result['monto'] = float(result['monto'])
        if isinstance(result.get('fecha'), date):
            result['fecha'] = result['fecha'].strftime('%Y-%m-%d')
        elif isinstance(result.get('fecha'), datetime):
            result['fecha'] = result['fecha'].strftime('%Y-%m-%d')
            
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating financial movement: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear el movimiento financiero"
        )

@router.put("/movimientos/{movimiento_id}", response_model=MovimientoFinanciero,
    dependencies=[Depends(PermissionDependency("facturacion", "editar"))]
)
async def update_movimiento_financiero(business_id: str,
    movimiento_id: str,
    movimiento_update: MovimientoFinancieroUpdate, scoped: ScopedClientContext = Depends(BusinessScopedClientDep)) -> Any:
    """Update a financial movement."""
    supabase = scoped.client
    
    try:
        # Verify movement exists and belongs to business
        existing = supabase.table("movimientos_financieros").select("*").eq("id", movimiento_id).eq("negocio_id", business_id).execute()
        if not existing.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Movimiento financiero no encontrado"
            )
        
        update_data = movimiento_update.dict(exclude_unset=True)
        if not update_data:
            return existing.data[0]
        
        # Validate category if being updated
        if "categoria_id" in update_data and update_data["categoria_id"]:
            categoria = supabase.table("categorias_financieras").select("tipo").eq("id", update_data["categoria_id"]).eq("negocio_id", business_id).execute()
            if not categoria.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Categoría no encontrada o no pertenece a este negocio"
                )
        
        response = (
            supabase
            .table("movimientos_financieros")
            .update(update_data)
            .eq("id", movimiento_id)
            .eq("negocio_id", business_id)
            .execute()
        )
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al actualizar el movimiento financiero"
            )
            
        return response.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating financial movement: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar el movimiento financiero"
        )

@router.delete("/movimientos/{movimiento_id}",
    dependencies=[Depends(PermissionDependency("facturacion", "editar"))]
)
async def delete_movimiento_financiero(business_id: str,
    movimiento_id: str, scoped: ScopedClientContext = Depends(BusinessScopedClientDep)) -> Any:
    """Delete a financial movement."""
    supabase = scoped.client
    
    try:
        # Verify movement exists and belongs to business
        existing = supabase.table("movimientos_financieros").select("id").eq("id", movimiento_id).eq("negocio_id", business_id).execute()
        if not existing.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Movimiento financiero no encontrado"
            )
        
        response = (
            supabase
            .table("movimientos_financieros")
            .delete()
            .eq("id", movimiento_id)
            .eq("negocio_id", business_id)
            .execute()
        )
        
        return {"message": "Movimiento financiero eliminado exitosamente"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting financial movement: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar el movimiento financiero"
        )

# ============================================================================
# DASHBOARD Y RESUMEN
# ============================================================================

@router.get("/resumen", response_model=ResumenFinanciero,
    dependencies=[Depends(PermissionDependency("facturacion", "ver"))]
)
async def get_resumen_financiero(
    request: Request,
    business_id: str,
    mes: Optional[int] = Query(None, ge=1, le=12),
    anio: Optional[int] = Query(None, ge=2020),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """Get financial summary for a business."""
    
    # Log de entrada para debugging
    logger.info(f"🔍 Iniciando get_resumen_financiero para business_id: {business_id}")
    
    try:
        supabase = scoped.client
        
        
    
        try:
            # Use current month/year if not provided
            now = datetime.now()
            target_mes = mes if mes is not None else now.month
            target_anio = anio if anio is not None else now.year
            
            logger.info(f"📊 Consultando datos financieros para {target_mes}/{target_anio}")
            
            # Calculate date ranges
            start_date = datetime(target_anio, target_mes, 1)
            if target_mes == 12:
                end_date = datetime(target_anio + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = datetime(target_anio, target_mes + 1, 1) - timedelta(days=1)
            
            # Previous month for comparison
            if target_mes == 1:
                prev_mes = 12
                prev_anio = target_anio - 1
            else:
                prev_mes = target_mes - 1
                prev_anio = target_anio
            
            prev_start_date = datetime(prev_anio, prev_mes, 1)
            if prev_mes == 12:
                prev_end_date = datetime(prev_anio + 1, 1, 1) - timedelta(days=1)
            else:
                prev_end_date = datetime(prev_anio, prev_mes + 1, 1) - timedelta(days=1)

            # Query current month movements
            movimientos_response = supabase.table("movimientos_financieros") \
                .select("tipo, monto") \
                .eq("negocio_id", business_id) \
                .gte("fecha", start_date.isoformat()) \
                .lte("fecha", end_date.isoformat()) \
                .execute()

            # Query previous month movements
            movimientos_prev_response = supabase.table("movimientos_financieros") \
                .select("tipo, monto") \
                .eq("negocio_id", business_id) \
                .gte("fecha", prev_start_date.isoformat()) \
                .lte("fecha", prev_end_date.isoformat()) \
                .execute()
            
            # Query current month sales (ventas)
            ventas_response = supabase.table("ventas") \
                .select("total") \
                .eq("negocio_id", business_id) \
                .gte("fecha", start_date.isoformat()) \
                .lte("fecha", end_date.isoformat()) \
                .execute()
            
            # Query previous month sales (ventas)
            ventas_prev_response = supabase.table("ventas") \
                .select("total") \
                .eq("negocio_id", business_id) \
                .gte("fecha", prev_start_date.isoformat()) \
                .lte("fecha", prev_end_date.isoformat()) \
                .execute()

            logger.info(f"📊 Movimientos actuales: {len(movimientos_response.data)}")
            logger.info(f"📊 Movimientos previos: {len(movimientos_prev_response.data)}")
            logger.info(f"💰 Ventas actuales: {len(ventas_response.data)}")
            logger.info(f"💰 Ventas previas: {len(ventas_prev_response.data)}")

            # Calculate totals for current month
            ingresos_movimientos = sum(
                float(mov["monto"]) for mov in movimientos_response.data 
                if mov["tipo"] == "ingreso"
            )
            ingresos_ventas = sum(
                float(venta["total"]) for venta in ventas_response.data
            )
            ingresos_mes = ingresos_movimientos + ingresos_ventas
            
            egresos_mes = sum(
                float(mov["monto"]) for mov in movimientos_response.data 
                if mov["tipo"] == "egreso"
            )

            # Calculate totals for previous month
            ingresos_movimientos_anterior = sum(
                float(mov["monto"]) for mov in movimientos_prev_response.data 
                if mov["tipo"] == "ingreso"
            )
            ingresos_ventas_anterior = sum(
                float(venta["total"]) for venta in ventas_prev_response.data
            )
            ingresos_mes_anterior = ingresos_movimientos_anterior + ingresos_ventas_anterior
            
            egresos_mes_anterior = sum(
                float(mov["monto"]) for mov in movimientos_prev_response.data 
                if mov["tipo"] == "egreso"
            )

            # Calculate current balance (simplified - you might want to calculate from all movements)
            saldo_actual = ingresos_mes - egresos_mes

            logger.info(f"💰 Resumen calculado - Ingresos: {ingresos_mes}, Egresos: {egresos_mes}, Saldo: {saldo_actual}")

            resumen_data = {
                "ingresos_mes": float(ingresos_mes),
                "egresos_mes": float(egresos_mes),
                "saldo_actual": float(saldo_actual),
                "ingresos_mes_anterior": float(ingresos_mes_anterior),
                "egresos_mes_anterior": float(egresos_mes_anterior)
            }
            
            return JSONResponse(status_code=200, content=resumen_data)

        except Exception as e:
            logger.error(f"❌ Error consultando datos financieros: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Error consultando datos financieros",
                    "error": "DATA_QUERY_ERROR",
                    "message": str(e)
                }
            )

    except Exception as e:
        logger.error(f"❌ Error general en get_resumen_financiero: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Error interno del servidor",
                "error": "INTERNAL_SERVER_ERROR",
                "message": str(e)
            }
        )

@router.get("/flujo-caja", response_model=FlujoCajaMensual,
    dependencies=[Depends(PermissionDependency("facturacion", "ver"))]
)
async def get_flujo_caja_mensual(
    business_id: str,
    mes: int = Query(..., ge=1, le=12),
    anio: int = Query(..., ge=2020),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """Get monthly cash flow for a business."""
    supabase = scoped.client
    
    try:
        # Calculate date range
        month_start = date(anio, mes, 1)
        month_end = date(anio, mes, calendar.monthrange(anio, mes)[1])
        
        # Get all movements for the month
        movements = supabase.table("movimientos_financieros").select("fecha, tipo, monto").eq("negocio_id", business_id).gte("fecha", month_start.isoformat()).lte("fecha", month_end.isoformat()).order("fecha").execute()
        
        # Get all sales for the month
        ventas = supabase.table("ventas").select("fecha, total").eq("negocio_id", business_id).gte("fecha", month_start.isoformat()).lte("fecha", month_end.isoformat()).order("fecha").execute()
        
        # Group by date and calculate daily totals
        daily_data = {}
        
        # Process manual financial movements
        for movement in movements.data if movements.data else []:
            fecha = datetime.fromisoformat(movement["fecha"]).date()
            if fecha not in daily_data:
                daily_data[fecha] = {"ingresos": Decimal("0"), "egresos": Decimal("0")}
            
            monto = Decimal(str(movement["monto"]))
            if movement["tipo"] == "ingreso":
                daily_data[fecha]["ingresos"] += monto
            else:
                daily_data[fecha]["egresos"] += monto
        
        # Process sales as income
        for venta in ventas.data if ventas.data else []:
            fecha = datetime.fromisoformat(venta["fecha"]).date()
            if fecha not in daily_data:
                daily_data[fecha] = {"ingresos": Decimal("0"), "egresos": Decimal("0")}
            
            monto = Decimal(str(venta["total"]))
            daily_data[fecha]["ingresos"] += monto
        
        # Generate daily flow with accumulated balance - only for dates with movements
        flujo_diario = []
        saldo_acumulado = Decimal("0")
        
        # Sort dates with movements and iterate only through those
        fechas_con_movimientos = sorted(daily_data.keys())
        
        for fecha in fechas_con_movimientos:
            day_data = daily_data[fecha]
            saldo_diario = day_data["ingresos"] - day_data["egresos"]
            saldo_acumulado += saldo_diario
            
            flujo_diario.append(FlujoCajaDiario(
                fecha=fecha.strftime('%Y-%m-%d'),  # Convertir date a string
                ingresos=day_data["ingresos"],      # Mantener como Decimal
                egresos=day_data["egresos"],        # Mantener como Decimal
                saldo_acumulado=saldo_acumulado     # Mantener como Decimal
            ))
        
        # Serializar datos para JSON
        flujo_serializado = {
            "mes": mes,
            "anio": anio,
            "flujo_diario": [serialize_for_json(d.dict()) for d in flujo_diario]
        }
        
        return JSONResponse(status_code=200, content=serialize_for_json(flujo_serializado))
        
    except Exception as e:
        logger.error(f"Error getting cash flow: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener el flujo de caja"
        )

# ============================================================================
# CUENTAS POR COBRAR Y POR PAGAR
# ============================================================================

@router.get("/cuentas-cobrar", response_model=List[CuentaPendienteConCliente],
    dependencies=[Depends(PermissionDependency("facturacion", "ver"))]
)
async def get_cuentas_por_cobrar(
    business_id: str,
    estado: Optional[str] = Query(None, regex="^(pendiente|pagado|vencido)$"),
    vencimiento_desde: Optional[date] = Query(None),
    vencimiento_hasta: Optional[date] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """Get accounts receivable for a business."""
    supabase = scoped.client
    
    try:
        query = supabase.table("cuentas_pendientes").select("""
            *,
            clientes(nombre, apellido)
        """).eq("negocio_id", business_id).eq("tipo", "por_cobrar")
        
        # Apply filters
        if estado:
            query = query.eq("estado", estado)
        if vencimiento_desde:
            query = query.gte("fecha_vencimiento", vencimiento_desde.isoformat())
        if vencimiento_hasta:
            query = query.lte("fecha_vencimiento", vencimiento_hasta.isoformat())
        
        # Order by due date (most urgent first)
        response = query.order("fecha_vencimiento").range(offset, offset + limit - 1).execute()
        
        # Transform data to include client names and calculate days to expiration
        cuentas = []
        today = date.today()
        
        for item in response.data if response.data else []:
            cuenta = CuentaPendienteConCliente(**item)
            
            # Add client name
            if item.get("clientes"):
                client = item["clientes"]
                cuenta.cliente_nombre = f"{client.get('nombre', '')} {client.get('apellido', '')}".strip()
            elif item.get("proveedor_nombre"):
                cuenta.cliente_nombre = item["proveedor_nombre"]
            
            # Calculate days to expiration
            vencimiento = datetime.fromisoformat(item["fecha_vencimiento"]).date()
            cuenta.dias_vencimiento = (vencimiento - today).days
            
            cuentas.append(cuenta)
        
        return JSONResponse(status_code=200, content=[serialize_for_json(c.dict()) for c in cuentas])
        
    except Exception as e:
        logger.error(f"Error fetching accounts receivable: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener las cuentas por cobrar"
        )

@router.get("/cuentas-pagar", response_model=List[CuentaPendienteConCliente],
    dependencies=[Depends(PermissionDependency("facturacion", "ver"))]
)
async def get_cuentas_por_pagar(
    business_id: str,
    estado: Optional[str] = Query(None, regex="^(pendiente|pagado|vencido)$"),
    vencimiento_desde: Optional[date] = Query(None),
    vencimiento_hasta: Optional[date] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """Get accounts payable for a business."""
    supabase = scoped.client
    
    try:
        query = supabase.table("cuentas_pendientes").select("""
            *,
            clientes(nombre, apellido)
        """).eq("negocio_id", business_id).eq("tipo", "por_pagar")
        
        # Apply filters
        if estado:
            query = query.eq("estado", estado)
        if vencimiento_desde:
            query = query.gte("fecha_vencimiento", vencimiento_desde.isoformat())
        if vencimiento_hasta:
            query = query.lte("fecha_vencimiento", vencimiento_hasta.isoformat())
        
        # Order by due date (most urgent first)
        response = query.order("fecha_vencimiento").range(offset, offset + limit - 1).execute()
        
        # Transform data to include client/supplier names and calculate days to expiration
        cuentas = []
        today = date.today()
        
        for item in response.data if response.data else []:
            cuenta = CuentaPendienteConCliente(**item)
            
            # Add client or supplier name
            if item.get("clientes"):
                client = item["clientes"]
                cuenta.cliente_nombre = f"{client.get('nombre', '')} {client.get('apellido', '')}".strip()
            elif item.get("proveedor_nombre"):
                cuenta.cliente_nombre = item["proveedor_nombre"]
            
            # Calculate days to expiration
            vencimiento = datetime.fromisoformat(item["fecha_vencimiento"]).date()
            cuenta.dias_vencimiento = (vencimiento - today).days
            
            cuentas.append(cuenta)
        
        return JSONResponse(status_code=200, content=[serialize_for_json(c.dict()) for c in cuentas])
        
    except Exception as e:
        logger.error(f"Error fetching accounts payable: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener las cuentas por pagar"
        )

@router.post("/cuentas", response_model=CuentaPendiente,
    dependencies=[Depends(PermissionDependency("facturacion", "editar"))]
)
async def create_cuenta_pendiente(
    business_id: str,
    cuenta_in: CuentaPendienteCreate,
    current_user: User = Depends(get_current_user),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """Create a new pending account (receivable or payable)."""
    supabase = scoped.client
    
    try:
        # Validate client belongs to business if provided
        if cuenta_in.cliente_id:
            cliente = supabase.table("clientes").select("id").eq("id", cuenta_in.cliente_id).eq("negocio_id", business_id).execute()
            if not cliente.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cliente no encontrado o no pertenece a este negocio"
                )
        
        # Validate that either cliente_id or proveedor_nombre is provided
        if not cuenta_in.cliente_id and not cuenta_in.proveedor_nombre:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debe especificar un cliente o nombre de proveedor"
            )
        
        cuenta_data = cuenta_in.dict()
        cuenta_data["negocio_id"] = business_id
        cuenta_data["creado_por"] = current_user.id
        
        response = supabase.table("cuentas_pendientes").insert(cuenta_data).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al crear la cuenta pendiente"
            )
            
        return response.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating pending account: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear la cuenta pendiente"
        )

@router.put("/cuentas/{cuenta_id}", response_model=CuentaPendiente,
    dependencies=[Depends(PermissionDependency("facturacion", "editar"))]
)
async def update_cuenta_pendiente(business_id: str,
    cuenta_id: str,
    cuenta_update: CuentaPendienteUpdate, scoped: ScopedClientContext = Depends(BusinessScopedClientDep)) -> Any:
    """Update a pending account."""
    supabase = scoped.client
    
    try:
        # Verify account exists and belongs to business
        existing = supabase.table("cuentas_pendientes").select("*").eq("id", cuenta_id).eq("negocio_id", business_id).execute()
        if not existing.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cuenta pendiente no encontrada"
            )
        
        update_data = cuenta_update.dict(exclude_unset=True)
        if not update_data:
            return existing.data[0]
        
        # Validate client if being updated
        if "cliente_id" in update_data and update_data["cliente_id"]:
            cliente = supabase.table("clientes").select("id").eq("id", update_data["cliente_id"]).eq("negocio_id", business_id).execute()
            if not cliente.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cliente no encontrado o no pertenece a este negocio"
                )
        
        response = (
            supabase
            .table("cuentas_pendientes")
            .update(update_data)
            .eq("id", cuenta_id)
            .eq("negocio_id", business_id)
            .execute()
        )
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al actualizar la cuenta pendiente"
            )
            
        return response.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating pending account: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar la cuenta pendiente"
        )

@router.put("/cuentas/{cuenta_id}/marcar-pagado",
    dependencies=[Depends(PermissionDependency("facturacion", "editar"))]
)
async def marcar_cuenta_como_pagada(
    business_id: str,
    cuenta_id: str,
    current_user: User = Depends(get_current_user),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """Mark an account as paid."""
    supabase = scoped.client
    
    try:
        # Verify account exists and belongs to business
        existing = supabase.table("cuentas_pendientes").select("*").eq("id", cuenta_id).eq("negocio_id", business_id).execute()
        if not existing.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cuenta pendiente no encontrada"
            )
        
        cuenta = existing.data[0]
        if cuenta["estado"] == "pagado":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La cuenta ya está marcada como pagada"
            )
        
        update_data = {
            "estado": "pagado",
            "pagado_en": datetime.now().isoformat(),
            "pagado_por": current_user.id
        }
        
        response = (
            supabase
            .table("cuentas_pendientes")
            .update(update_data)
            .eq("id", cuenta_id)
            .eq("negocio_id", business_id)
            .execute()
        )
        
        return {"message": "Cuenta marcada como pagada exitosamente"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking account as paid: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al marcar la cuenta como pagada"
        )

@router.delete("/cuentas/{cuenta_id}",
    dependencies=[Depends(PermissionDependency("facturacion", "editar"))]
)
async def delete_cuenta_pendiente(business_id: str,
    cuenta_id: str, scoped: ScopedClientContext = Depends(BusinessScopedClientDep)) -> Any:
    """Delete a pending account."""
    supabase = scoped.client
    
    try:
        # Verify account exists and belongs to business
        existing = supabase.table("cuentas_pendientes").select("id").eq("id", cuenta_id).eq("negocio_id", business_id).execute()
        if not existing.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cuenta pendiente no encontrada"
            )
        
        response = (
            supabase
            .table("cuentas_pendientes")
            .delete()
            .eq("id", cuenta_id)
            .eq("negocio_id", business_id)
            .execute()
        )
        
        return {"message": "Cuenta pendiente eliminada exitosamente"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting pending account: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar la cuenta pendiente"
        )
