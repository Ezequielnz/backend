import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status

from app import types
from app.api.context import BusinessScopedClientDep, ScopedClientContext

router = APIRouter()
logger = logging.getLogger(__name__)


def _normalize_branch_settings(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    model_dump = getattr(raw, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    return {}


def _resolve_branch_id(scoped: ScopedClientContext, settings: Dict[str, Any]) -> Optional[str]:
    branch_id = getattr(scoped.context, "branch_id", None)
    if branch_id:
        return str(branch_id)
    default_branch = settings.get("default_branch_id")
    if default_branch:
        return str(default_branch)
    return None


def _fetch_main_branch_id(supabase, business_id: str) -> Optional[str]:
    response = (
        supabase.table("sucursales")
        .select("id")
        .eq("negocio_id", business_id)
        .eq("activo", True)
        .eq("is_main", True)
        .limit(1)
        .execute()
    )
    if response.data:
        branch = response.data[0]
        branch_id = branch.get("id")
        if branch_id:
            return str(branch_id)

    fallback = (
        supabase.table("sucursales")
        .select("id")
        .eq("negocio_id", business_id)
        .eq("activo", True)
        .limit(1)
        .execute()
    )
    if fallback.data:
        branch_id = fallback.data[0].get("id")
        if branch_id:
            return str(branch_id)
    return None


def _ensure_inventory_branch(
    supabase,
    business_id: str,
    scoped: ScopedClientContext,
    settings: Dict[str, Any],
) -> str:
    branch_id = _resolve_branch_id(scoped, settings)
    if branch_id:
        return branch_id
    fallback = _fetch_main_branch_id(supabase, business_id)
    if fallback:
        return fallback
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="El negocio no tiene una sucursal seleccionada ni principal para operar stock por sucursal.",
    )


def _list_active_branch_ids(supabase, business_id: str) -> List[str]:
    response = (
        supabase.table("sucursales")
        .select("id")
        .eq("negocio_id", business_id)
        .eq("activo", True)
        .execute()
    )
    branch_ids: List[str] = []
    for row in response.data or []:
        branch_id = row.get("id")
        if branch_id:
            branch_ids.append(str(branch_id))
    return branch_ids


def _upsert_inventory_negocio(supabase, business_id: str, producto_id: Any, stock_total: Any) -> None:
    payload = {
        "negocio_id": business_id,
        "producto_id": str(producto_id),
        "stock_total": float(stock_total or 0),
    }
    supabase.table("inventario_negocio").upsert(payload, on_conflict="negocio_id,producto_id").execute()


def _upsert_inventory_sucursal(
    supabase,
    business_id: str,
    sucursal_id: str,
    producto_id: Any,
    stock_actual: Any,
) -> None:
    payload = {
        "negocio_id": business_id,
        "sucursal_id": sucursal_id,
        "producto_id": str(producto_id),
        "stock_actual": float(stock_actual or 0),
    }
    supabase.table("inventario_sucursal").upsert(
        payload,
        on_conflict="sucursal_id,producto_id",
    ).execute()


def _upsert_catalog_records(
    supabase,
    business_id: str,
    producto_id: Any,
    branch_ids: List[str],
    *,
    precio_venta: Optional[Any] = None,
    precio_compra: Optional[Any] = None,
    stock_minimo: Optional[Any] = None,
    codigo: Optional[str] = None,
) -> None:
    if not branch_ids:
        return

    payload_base: Dict[str, Any] = {
        "negocio_id": business_id,
        "producto_id": str(producto_id),
    }
    if precio_venta is not None:
        payload_base["precio"] = float(precio_venta)
    if precio_compra is not None:
        payload_base["precio_costo"] = float(precio_compra)
    if stock_minimo is not None:
        payload_base["stock_minimo"] = float(stock_minimo)
    if codigo:
        payload_base["sku_local"] = codigo

    if len(payload_base) == 2:  # No hay campos específicos para actualizar
        return

    for branch_id in branch_ids:
        payload = dict(payload_base)
        payload["sucursal_id"] = branch_id
        payload.setdefault("estado", "activo")
        payload.setdefault("visibilidad", "publico")
        try:
            supabase.table("producto_sucursal").upsert(
                payload,
                on_conflict="producto_id,sucursal_id",
            ).execute()
        except Exception as exc:  # pragma: no cover - defensivo ante errores de Supabase
            logger.warning(
                "No se pudo sincronizar producto_sucursal para producto %s en sucursal %s: %s",
                producto_id,
                branch_id,
                exc,
            )
@router.get("/", response_model=List[types.Producto])
async def get_productos(
    business_id: str,
    skip: int = 0,
    limit: int = 100,
    only_active: bool = True,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """
    Obtener listado de productos considerando el modo de inventario y el catálogo por sucursal.
    """
    supabase = scoped.client
    settings = _normalize_branch_settings(scoped.context.branch_settings)
    inventory_mode = settings.get("inventario_modo", "por_sucursal")
    catalog_mode = settings.get("catalogo_producto_modo", "por_sucursal")

    query = supabase.table("productos").select("*").eq("negocio_id", business_id)

    if only_active:
        query = query.eq("activo", True)

    response = query.range(skip, skip + limit - 1).execute()
    productos = response.data or []

    if not productos:
        return []

    producto_ids = [str(prod.get("id")) for prod in productos if prod.get("id")]
    if not producto_ids:
        return productos

    stock_map: Dict[str, float] = {}
    catalog_map: Dict[str, Dict[str, Any]] = {}

    try:
        if inventory_mode == "centralizado":
            stock_resp = (
                supabase.table("inventario_negocio")
                .select("producto_id, stock_total")
                .in_("producto_id", producto_ids)
                .execute()
            )
            for row in stock_resp.data or []:
                producto_id = str(row.get("producto_id"))
                stock_map[producto_id] = float(row.get("stock_total") or 0.0)
        else:
            branch_id = _ensure_inventory_branch(supabase, business_id, scoped, settings)
            stock_resp = (
                supabase.table("inventario_sucursal")
                .select("producto_id, stock_actual")
                .eq("sucursal_id", branch_id)
                .in_("producto_id", producto_ids)
                .execute()
            )
            for row in stock_resp.data or []:
                producto_id = str(row.get("producto_id"))
                stock_map[producto_id] = float(row.get("stock_actual") or 0.0)

            catalog_resp = (
                supabase.table("producto_sucursal")
                .select("producto_id, precio, precio_costo, stock_minimo, estado, visibilidad, sku_local")
                .eq("sucursal_id", branch_id)
                .in_("producto_id", producto_ids)
                .execute()
            )
            for row in catalog_resp.data or []:
                producto_id = str(row.get("producto_id"))
                catalog_map[producto_id] = row

        # Cuando el catálogo es compartido también sincronizamos datos de la sucursal activa.
        if inventory_mode == "centralizado" and catalog_mode == "compartido":
            branch_id = _resolve_branch_id(scoped, settings)
            if branch_id:
                catalog_resp = (
                    supabase.table("producto_sucursal")
                    .select("producto_id, precio, precio_costo, stock_minimo, estado, visibilidad, sku_local")
                    .eq("sucursal_id", branch_id)
                    .in_("producto_id", producto_ids)
                    .execute()
                )
                for row in catalog_resp.data or []:
                    producto_id = str(row.get("producto_id"))
                    catalog_map[producto_id] = row
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("No se pudo obtener el stock consolidado para el negocio %s", business_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo obtener el inventario consolidado del negocio.",
        ) from exc

    for producto in productos:
        producto_id = str(producto.get("id"))
        if producto_id in stock_map:
            producto["stock_actual"] = stock_map[producto_id]
        else:
            producto.setdefault("stock_actual", 0)

        catalog_entry = catalog_map.get(producto_id)
        if catalog_entry:
            if catalog_entry.get("precio") is not None:
                producto["precio_venta"] = float(catalog_entry["precio"])
            if catalog_entry.get("precio_costo") is not None:
                producto["precio_compra"] = float(catalog_entry["precio_costo"])
            if catalog_entry.get("stock_minimo") is not None:
                producto["stock_minimo"] = float(catalog_entry["stock_minimo"])
            if catalog_entry.get("estado") and catalog_entry["estado"] != "activo":
                producto["activo"] = False

    return productos


@router.post("/", response_model=types.Producto)
async def create_producto(
    *,
    business_id: str,
    producto_in: types.ProductoCreate,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """
    Crear un nuevo producto para un negocio.
    """
    supabase = scoped.client

    if producto_in.codigo:
        existing = (
            supabase.table("productos")
            .select("id")
            .eq("negocio_id", business_id)
            .eq("codigo", producto_in.codigo)
            .limit(1)
            .execute()
        )
        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe un producto con este código en el negocio.",
            )

    payload = producto_in.model_dump()
    payload["negocio_id"] = business_id

    settings = _normalize_branch_settings(scoped.context.branch_settings)
    inventory_mode = settings.get("inventario_modo", "por_sucursal")
    catalog_mode = settings.get("catalogo_producto_modo", "por_sucursal")

    try:
        response = supabase.table("productos").insert(payload).execute()
    except Exception as exc:
        logger.exception("No se pudo crear el producto para el negocio %s", business_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear el producto en la base de datos.",
        ) from exc

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear el producto",
        )

    producto = response.data[0]
    producto_id = producto.get("id")

    try:
        if inventory_mode == "centralizado":
            _upsert_inventory_negocio(supabase, business_id, producto_id, producto_in.stock_actual)
        else:
            branch_id = _ensure_inventory_branch(supabase, business_id, scoped, settings)
            _upsert_inventory_sucursal(
                supabase,
                business_id,
                branch_id,
                producto_id,
                producto_in.stock_actual,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("No se pudo sincronizar inventario para el producto %s", producto_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="El producto se creó pero no se pudo sincronizar el inventario.",
        ) from exc

    try:
        if catalog_mode == "compartido":
            branch_ids = _list_active_branch_ids(supabase, business_id)
        else:
            branch_ids = [
                _ensure_inventory_branch(supabase, business_id, scoped, settings)
            ]

        _upsert_catalog_records(
            supabase,
            business_id,
            producto_id,
            branch_ids,
            precio_venta=producto_in.precio_venta,
            precio_compra=producto_in.precio_compra,
            stock_minimo=producto_in.stock_minimo,
            codigo=producto_in.codigo,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "No se pudo sincronizar producto_sucursal para el producto %s: %s",
            producto_id,
            exc,
        )

    producto["stock_actual"] = float(producto_in.stock_actual)
    if producto_in.stock_minimo is not None:
        producto["stock_minimo"] = float(producto_in.stock_minimo)

    return producto


@router.get("/{producto_id}", response_model=types.Producto)
async def get_producto(
    *,
    business_id: str,
    producto_id: int,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """
    Obtener un producto por ID dentro de un negocio.
    """
    supabase = scoped.client
    response = (
        supabase.table("productos")
        .select("*")
        .eq("negocio_id", business_id)
        .eq("id", producto_id)
        .maybe_single()
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado en este negocio",
        )

    return response.data


@router.put("/{producto_id}", response_model=types.Producto)
async def update_producto(
    *,
    business_id: str,
    producto_id: int,
    producto_in: types.ProductoUpdate,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """
    Actualizar un producto de un negocio.
    """
    supabase = scoped.client
    exists = (
        supabase.table("productos")
        .select("id")
        .eq("negocio_id", business_id)
        .eq("id", producto_id)
        .limit(1)
        .execute()
    )
    if not exists.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado en este negocio",
        )

    settings = _normalize_branch_settings(scoped.context.branch_settings)
    inventory_mode = settings.get("inventario_modo", "por_sucursal")
    catalog_mode = settings.get("catalogo_producto_modo", "por_sucursal")

    update_data = producto_in.model_dump(exclude_unset=True)
    stock_update = update_data.pop("stock_actual", None)
    precio_update = update_data.get("precio_venta")
    precio_compra_update = update_data.get("precio_compra")
    stock_minimo_update = update_data.get("stock_minimo")

    updated_product: Optional[Dict[str, Any]] = None

    if update_data:
        try:
            response = (
                supabase.table("productos")
                .update(update_data)
                .eq("negocio_id", business_id)
                .eq("id", producto_id)
                .execute()
            )
        except Exception as exc:
            logger.exception("No se pudo actualizar el producto %s en Supabase", producto_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al actualizar el producto",
            ) from exc

        if response.data:
            updated_product = response.data[0]

    try:
        if stock_update is not None:
            if inventory_mode == "centralizado":
                _upsert_inventory_negocio(supabase, business_id, producto_id, stock_update)
            else:
                branch_id = _ensure_inventory_branch(supabase, business_id, scoped, settings)
                _upsert_inventory_sucursal(
                    supabase,
                    business_id,
                    branch_id,
                    producto_id,
                    stock_update,
                )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("No se pudo sincronizar inventario para el producto %s", producto_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo sincronizar el inventario del producto actualizado.",
        ) from exc

    try:
        if any(value is not None for value in (precio_update, precio_compra_update, stock_minimo_update)):
            if catalog_mode == "compartido":
                branch_ids = _list_active_branch_ids(supabase, business_id)
            else:
                branch_ids = [
                    _ensure_inventory_branch(supabase, business_id, scoped, settings)
                ]
            _upsert_catalog_records(
                supabase,
                business_id,
                producto_id,
                branch_ids,
                precio_venta=precio_update,
                precio_compra=precio_compra_update,
                stock_minimo=stock_minimo_update,
                codigo=update_data.get("codigo"),
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "No se pudo sincronizar producto_sucursal durante la actualización del producto %s: %s",
            producto_id,
            exc,
        )

    if updated_product is None:
        refreshed = (
            supabase.table("productos")
            .select("*")
            .eq("negocio_id", business_id)
            .eq("id", producto_id)
            .limit(1)
            .execute()
        )
        if refreshed.data:
            updated_product = refreshed.data[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No se pudo cargar el producto actualizado.",
            )

    if stock_update is not None:
        updated_product["stock_actual"] = float(stock_update)
    return updated_product


@router.delete("/{producto_id}", response_model=types.Producto)
async def delete_producto(
    *,
    business_id: str,
    producto_id: int,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """
    Desactivar un producto dentro de un negocio.
    """
    supabase = scoped.client
    exists = (
        supabase.table("productos")
        .select("id")
        .eq("negocio_id", business_id)
        .eq("id", producto_id)
        .limit(1)
        .execute()
    )
    if not exists.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado en este negocio",
        )

    response = (
        supabase.table("productos")
        .update({"activo": False})
        .eq("negocio_id", business_id)
        .eq("id", producto_id)
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al desactivar el producto",
        )

    return response.data[0]


@router.post("/importar")
async def importar_productos(
    *,
    business_id: str,
    file: UploadFile = File(...),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
) -> Any:
    """
    Importar productos desde un archivo (placeholder).
    """
    _ = scoped.client  # placeholder for futura integración
    return {
        "message": f"Archivo {file.filename} importado correctamente",
        "negocio_id": business_id,
    }
