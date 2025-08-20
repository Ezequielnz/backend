from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from datetime import datetime, date
import uuid
import jwt

from app.db.supabase_client import get_supabase_user_client
from app.dependencies import PermissionDependency
from app.schemas.compra import CompraCreate, CompraUpdate

router = APIRouter()


def _get_user_id_from_token(authorization: str) -> str:
    try:
        token = authorization or ""
        if token.startswith("Bearer "):
            token = token[7:]
        decoded = jwt.decode(token, options={"verify_signature": False})
        user_id = decoded.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token JWT inválido: no contiene user_id")
        return user_id
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Error al procesar token: {str(e)}")


@router.get(
    "/",
    dependencies=[Depends(PermissionDependency("stock", "ver"))]
)
@router.get(
    "",
    dependencies=[Depends(PermissionDependency("stock", "ver"))]
)
async def read_purchases(
    business_id: str,
    request: Request,
    desde: Optional[str] = Query(None, description="Fecha inicio (YYYY-MM-DD)"),
    hasta: Optional[str] = Query(None, description="Fecha fin (YYYY-MM-DD)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Any:
    """
    Lista compras del negocio. Requiere permiso stock/ver.
    """
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token requerido")

    client = get_supabase_user_client(authorization)

    try:
        query = client.table("compras").select("*").eq("negocio_id", business_id)
        if desde:
            query = query.gte("fecha_compra", desde)
        if hasta:
            query = query.lte("fecha_compra", hasta)
        if offset or limit:
            query = query.range(offset, offset + limit - 1)

        resp = query.order("fecha_compra", desc=True).execute()
        data = resp.data or []
        # Backward-compat: frontend expects field 'fecha'
        for row in data:
            if "fecha" not in row:
                row["fecha"] = row.get("fecha_compra")
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener compras: {str(e)}")


@router.get(
    "/{compra_id}",
    dependencies=[Depends(PermissionDependency("stock", "ver"))]
)
async def read_purchase(
    business_id: str,
    compra_id: str,
    request: Request,
) -> Any:
    """
    Obtiene una compra con sus items.
    """
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token requerido")

    client = get_supabase_user_client(authorization)

    try:
        compra_resp = (
            client
            .table("compras")
            .select("*")
            .eq("id", compra_id)
            .eq("negocio_id", business_id)
            .single()
            .execute()
        )
        compra = compra_resp.data
        if not compra:
            raise HTTPException(status_code=404, detail="Compra no encontrada")
        # Backward-compat: frontend expects field 'fecha'
        compra.setdefault("fecha", compra.get("fecha_compra"))

        detalle_resp = (
            client
            .table("compras_detalle")
            .select("id, producto_id, cantidad, precio_unitario, subtotal, productos(nombre)")
            .eq("compra_id", compra_id)
            .execute()
        )
        compra["items"] = detalle_resp.data or []
        return compra
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener compra: {str(e)}")


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionDependency("stock", "editar"))]
)
@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionDependency("stock", "editar"))]
)
async def create_purchase(
    business_id: str,
    compra_in: CompraCreate,
    request: Request,
) -> Any:
    """
    Crea una compra con items. Aumenta stock de productos comprados.
    """
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token requerido")

    client = get_supabase_user_client(authorization)

    try:
        user_id = _get_user_id_from_token(authorization)

        # Obtener usuario_negocio_id para este business
        un_resp = (
            client
            .table("usuarios_negocios")
            .select("id")
            .eq("usuario_id", user_id)
            .eq("negocio_id", business_id)
            .eq("estado", "aceptado")
            .limit(1)
            .execute()
        )
        if not un_resp.data:
            raise HTTPException(status_code=403, detail="No tienes acceso a este negocio")
        usuario_negocio_id = un_resp.data[0]["id"]

        # Validar proveedor si viene
        if compra_in.proveedor_id:
            prov_resp = (
                client
                .table("proveedores")
                .select("id")
                .eq("id", compra_in.proveedor_id)
                .eq("negocio_id", business_id)
                .execute()
            )
            if not prov_resp.data:
                raise HTTPException(status_code=404, detail="Proveedor no encontrado o no pertenece a este negocio")

        # Validar productos y preparar items
        items_preparados: List[dict] = []
        total = 0.0
        for it in compra_in.items:
            prod_resp = (
                client
                .table("productos")
                .select("id, nombre, stock_actual")
                .eq("id", it.producto_id)
                .eq("negocio_id", business_id)
                .execute()
            )
            if not prod_resp.data:
                raise HTTPException(status_code=404, detail=f"Producto {it.producto_id} no encontrado o no pertenece al negocio")
            subtotal = float(it.cantidad) * float(it.precio_unitario)
            total += subtotal
            items_preparados.append({
                "producto_id": it.producto_id,
                "cantidad": int(it.cantidad),
                "precio_unitario": float(it.precio_unitario),
                "subtotal": subtotal,
            })

        compra_id = str(uuid.uuid4())
        fecha_value = (compra_in.fecha.isoformat() if isinstance(compra_in.fecha, date) else datetime.utcnow().date().isoformat())

        compra_data = {
            "id": compra_id,
            "negocio_id": business_id,
            "usuario_negocio_id": usuario_negocio_id,
            "proveedor_id": compra_in.proveedor_id,
            # Nota: la columna en DB es 'fecha_compra'
            "fecha_compra": fecha_value,
            "observaciones": compra_in.observaciones,
            "total": total,
        }

        # Insertar compra
        compra_resp = client.table("compras").insert(compra_data).execute()
        if not compra_resp.data:
            raise HTTPException(status_code=500, detail="Error al crear la compra")

        # Insertar detalle
        for it in items_preparados:
            it["compra_id"] = compra_id
        det_resp = client.table("compras_detalle").insert(items_preparados).execute()
        if not det_resp.data:
            # rollback header
            client.table("compras").delete().eq("id", compra_id).execute()
            raise HTTPException(status_code=500, detail="Error al crear el detalle de compra")

        # Actualizar stock de productos: incrementar
        for it in items_preparados:
            prod_resp2 = (
                client
                .table("productos")
                .select("stock_actual")
                .eq("id", it["producto_id"])
                .eq("negocio_id", business_id)
                .execute()
            )
            if prod_resp2.data:
                actual = prod_resp2.data[0].get("stock_actual", 0) or 0
                nuevo = int(actual) + int(it["cantidad"])
                client.table("productos").update({"stock_actual": nuevo}).eq("id", it["producto_id"]).eq("negocio_id", business_id).execute()

        # Retornar compra con items
        compra_result = compra_resp.data[0]
        # Backward-compat campo 'fecha'
        compra_result["fecha"] = compra_result.get("fecha_compra")
        compra_result["items"] = det_resp.data
        return compra_result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al crear compra: {str(e)}")


@router.put(
    "/{compra_id}",
    dependencies=[Depends(PermissionDependency("stock", "editar"))]
)
async def update_purchase(
    business_id: str,
    compra_id: str,
    compra_update: CompraUpdate,
    request: Request,
) -> Any:
    """
    Actualiza campos de cabecera de la compra (proveedor, fecha, observaciones).
    No modifica items ni stock en esta versión.
    """
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token requerido")

    client = get_supabase_user_client(authorization)

    try:
        update_data = compra_update.model_dump(exclude_unset=True)
        # Alinear nombre de columnas: mover 'fecha' -> 'fecha_compra'
        if "fecha" in update_data:
            if isinstance(update_data["fecha"], date):
                update_data["fecha_compra"] = update_data["fecha"].isoformat()
            else:
                update_data["fecha_compra"] = update_data["fecha"]
            del update_data["fecha"]
        # Omitir campos no existentes en DB, como 'proveedor_nombre'
        update_data.pop("proveedor_nombre", None)

        # Validar proveedor si cambia
        if update_data.get("proveedor_id"):
            prov_resp = (
                client
                .table("proveedores")
                .select("id")
                .eq("id", update_data["proveedor_id"])
                .eq("negocio_id", business_id)
                .execute()
            )
            if not prov_resp.data:
                raise HTTPException(status_code=404, detail="Proveedor no encontrado o no pertenece a este negocio")

        resp = (
            client
            .table("compras")
            .update(update_data)
            .eq("id", compra_id)
            .eq("negocio_id", business_id)
            .execute()
        )
        if not resp.data:
            raise HTTPException(status_code=404, detail="Compra no encontrada o sin cambios")
        return resp.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al actualizar compra: {str(e)}")


@router.delete(
    "/{compra_id}",
    dependencies=[Depends(PermissionDependency("stock", "editar"))]
)
async def delete_purchase(
    business_id: str,
    compra_id: str,
    request: Request,
) -> Any:
    """
    Elimina una compra. Revierte el stock de los productos (disminuye la cantidad de los items).
    """
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token requerido")

    client = get_supabase_user_client(authorization)

    try:
        # Obtener detalle antes de eliminar
        det_resp = (
            client
            .table("compras_detalle")
            .select("producto_id, cantidad")
            .eq("compra_id", compra_id)
            .execute()
        )
        items = det_resp.data or []

        # Eliminar detalle primero
        client.table("compras_detalle").delete().eq("compra_id", compra_id).execute()
        # Eliminar cabecera
        header_resp = client.table("compras").delete().eq("id", compra_id).eq("negocio_id", business_id).execute()
        if not header_resp.data:
            raise HTTPException(status_code=404, detail="Compra no encontrada")

        # Revertir stock
        for it in items:
            prod_resp = (
                client
                .table("productos")
                .select("stock_actual")
                .eq("id", it["producto_id"])
                .eq("negocio_id", business_id)
                .execute()
            )
            if prod_resp.data:
                actual = prod_resp.data[0].get("stock_actual", 0) or 0
                nuevo = int(actual) - int(it["cantidad"])
                if nuevo < 0:
                    nuevo = 0
                client.table("productos").update({"stock_actual": nuevo}).eq("id", it["producto_id"]).eq("negocio_id", business_id).execute()

        return {"message": "Compra eliminada correctamente"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar compra: {str(e)}")
