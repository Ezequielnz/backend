from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from datetime import datetime, date
import uuid
import jwt

from app.db.supabase_client import get_supabase_service_client
from app.db.scoped_client import get_scoped_supabase_user_client
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

    client = get_scoped_supabase_user_client(authorization, business_id)

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

    client = get_scoped_supabase_user_client(authorization, business_id)

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

    client = get_scoped_supabase_user_client(authorization, business_id)

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
        proveedor_nombre: Optional[str] = getattr(compra_in, "proveedor_nombre", None)
        if compra_in.proveedor_id:
            prov_resp = (
                client
                .table("proveedores")
                .select("id, nombre")
                .eq("id", compra_in.proveedor_id)
                .eq("negocio_id", business_id)
                .execute()
            )
            if not prov_resp.data:
                raise HTTPException(status_code=404, detail="Proveedor no encontrado o no pertenece a este negocio")
            else:
                proveedor_nombre = prov_resp.data[0].get("nombre")

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
        # Normalizar fecha: aceptar date o string YYYY-MM-DD, sino hoy
        _f_tmp = getattr(compra_in, "fecha", None)
        if isinstance(_f_tmp, date):
            fecha_value = _f_tmp.isoformat()
        elif isinstance(_f_tmp, str):
            fecha_value = _f_tmp
        else:
            fecha_value = datetime.utcnow().date().isoformat()
        # Normalizar fecha_entrega con seguridad
        _fe_tmp = getattr(compra_in, "fecha_entrega", None)
        if isinstance(_fe_tmp, date):
            fecha_entrega_value: Optional[str] = _fe_tmp.isoformat()
        elif isinstance(_fe_tmp, str):
            fecha_entrega_value = _fe_tmp
        else:
            fecha_entrega_value = None

        # Estado de entrega: normalizar a 'entregado' | 'no_entregado' (default)
        _estado_tmp = getattr(compra_in, "estado", None)
        if isinstance(_estado_tmp, str):
            _norm = _estado_tmp.strip().lower().replace(" ", "_").replace("-", "_")
        else:
            _norm = "no_entregado"
        estado_value = _norm if _norm in {"entregado", "no_entregado"} else "no_entregado"

        compra_data = {
            "id": compra_id,
            "negocio_id": business_id,
            "usuario_negocio_id": usuario_negocio_id,
            "proveedor_id": compra_in.proveedor_id,
            # Nota: la columna en DB es 'fecha_compra'
            "fecha_compra": fecha_value,
            # Método de pago requerido por la tabla compras (NOT NULL)
            "metodo_pago": (getattr(compra_in, "metodo_pago", None) or "efectivo"),
            # Estado de entrega requerido por la tabla compras (NOT NULL)
            "estado": estado_value,
            "observaciones": compra_in.observaciones,
            "total": total,
        }
        # Incluir fecha_entrega sólo si viene informada
        if fecha_entrega_value is not None:
            compra_data["fecha_entrega"] = fecha_entrega_value

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

        # Actualizar stock de productos SOLO si la compra está entregada
        if estado_value == "entregado":
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
                    client.table("productos").update({
                        "stock_actual": nuevo,
                        "precio_compra": float(it["precio_unitario"]) if it.get("precio_unitario") is not None else None,
                    }).eq("id", it["producto_id"]).eq("negocio_id", business_id).execute()

        # Registrar gasto en finanzas
        try:
            svc = get_supabase_service_client()
            categoria_id = None
            try:
                cat_resp = (
                    svc
                    .table("categorias_financieras")
                    .select("id")
                    .eq("negocio_id", business_id)
                    .eq("tipo", "egreso")
                    .eq("nombre", "Compras")
                    .limit(1)
                    .execute()
                )
                if cat_resp.data:
                    categoria_id = cat_resp.data[0]["id"]
                else:
                    # Crear categoría 'Compras' si no existe
                    create_cat = (
                        svc
                        .table("categorias_financieras")
                        .insert({
                            "negocio_id": business_id,
                            "nombre": "Compras",
                            "descripcion": "Compras y aprovisionamiento",
                            "tipo": "egreso",
                            "activo": True,
                            "creado_por": user_id,
                        })
                        .execute()
                    )
                    if create_cat.data:
                        categoria_id = create_cat.data[0]["id"]
            except Exception as e:
                # Si falla buscar/crear categoría, continuar sin categoría
                print(f"[WARN] Categoría 'Compras' no disponible: {e}")

            movimiento_data = {
                "negocio_id": business_id,
                "tipo": "egreso",
                "categoria_id": categoria_id,
                "monto": float(total),
                "fecha": fecha_value,
                "metodo_pago": "compra",
                "descripcion": f"Compra {('a ' + proveedor_nombre) if proveedor_nombre else ''}".strip(),
                "observaciones": compra_in.observaciones or f"Compra {compra_id}",
                "cliente_id": None,
                "venta_id": None,
                "creado_por": user_id,
            }
            svc.table("movimientos_financieros").insert(movimiento_data).execute()
        except Exception as e:
            print(f"⚠️ No se pudo registrar movimiento financiero para la compra {compra_id}: {str(e)}")

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

    client = get_scoped_supabase_user_client(authorization, business_id)

    try:
        update_data = compra_update.model_dump(exclude_unset=True)
        # Alinear nombre de columnas: mover 'fecha' -> 'fecha_compra'
        if "fecha" in update_data:
            if isinstance(update_data["fecha"], date):
                update_data["fecha_compra"] = update_data["fecha"].isoformat()
            else:
                update_data["fecha_compra"] = update_data["fecha"]
            del update_data["fecha"]
        # Normalizar fecha_entrega a string ISO si viene como date
        if "fecha_entrega" in update_data and isinstance(update_data["fecha_entrega"], date):
            update_data["fecha_entrega"] = update_data["fecha_entrega"].isoformat()
        # Omitir campos no existentes en DB, como 'proveedor_nombre'
        update_data.pop("proveedor_nombre", None)

        # Normalizar estado si viene y obtener estado actual para decidir ajuste de stock
        if "estado" in update_data and isinstance(update_data["estado"], str):
            _norm = update_data["estado"].strip().lower().replace(" ", "_").replace("-", "_")
            update_data["estado"] = _norm if _norm in {"entregado", "no_entregado"} else "no_entregado"

        # Leer estado actual de la compra
        current_resp = (
            client
            .table("compras")
            .select("id, estado")
            .eq("id", compra_id)
            .eq("negocio_id", business_id)
            .single()
            .execute()
        )
        if not current_resp.data:
            raise HTTPException(status_code=404, detail="Compra no encontrada")
        current_estado = current_resp.data.get("estado")

        # Si el estado cambia, ajustar stock en consecuencia
        new_estado = update_data.get("estado")
        if new_estado and new_estado != current_estado:
            # Obtener items de la compra
            det_resp = (
                client
                .table("compras_detalle")
                .select("producto_id, cantidad, precio_unitario")
                .eq("compra_id", compra_id)
                .execute()
            )
            items = det_resp.data or []
            if current_estado != "entregado" and new_estado == "entregado":
                # Incrementar stock y actualizar precio_compra
                for it in items:
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
                        client.table("productos").update({
                            "stock_actual": nuevo,
                            "precio_compra": float(it["precio_unitario"]) if it.get("precio_unitario") is not None else None,
                        }).eq("id", it["producto_id"]).eq("negocio_id", business_id).execute()
            elif current_estado == "entregado" and new_estado != "entregado":
                # Decrementar stock (sin ir por debajo de 0)
                for it in items:
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
                        nuevo = int(actual) - int(it["cantidad"])
                        if nuevo < 0:
                            nuevo = 0
                        client.table("productos").update({
                            "stock_actual": nuevo,
                        }).eq("id", it["producto_id"]).eq("negocio_id", business_id).execute()

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
        updated = resp.data[0]
        updated.setdefault("fecha", updated.get("fecha_compra"))
        return updated
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

    client = get_scoped_supabase_user_client(authorization, business_id)

    try:
        # Obtener cabecera y detalle antes de eliminar
        header_sel = (
            client
            .table("compras")
            .select("id, estado")
            .eq("id", compra_id)
            .eq("negocio_id", business_id)
            .single()
            .execute()
        )
        if not header_sel.data:
            raise HTTPException(status_code=404, detail="Compra no encontrada")
        estado_actual = header_sel.data.get("estado")

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

        # Revertir stock solo si estaba entregada
        if estado_actual == "entregado":
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
