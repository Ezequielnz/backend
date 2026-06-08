from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from app.db.supabase_client import get_supabase_service_client

logger = logging.getLogger(__name__)

class SyncService:
    """
    Handles synchronization of data when business modes change
    (e.g., switching from centralizado to por_sucursal and vice versa).
    All operations use the service client to bypass RLS.
    """

    def __init__(self, business_id: str):
        self._business_id = business_id
        # Use service client to bypass RLS for mass sync operations
        self._client = get_supabase_service_client()

    def _get_main_branch_id(self) -> Optional[str]:
        response = (
            self._client.table("sucursales")
            .select("id")
            .eq("negocio_id", self._business_id)
            .eq("activo", True)
            .eq("is_main", True)
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0]["id"]
            
        # fallback to any active branch
        response = (
            self._client.table("sucursales")
            .select("id")
            .eq("negocio_id", self._business_id)
            .eq("activo", True)
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0]["id"]
        return None

    def _get_all_active_branch_ids(self) -> List[str]:
        response = (
            self._client.table("sucursales")
            .select("id")
            .eq("negocio_id", self._business_id)
            .eq("activo", True)
            .execute()
        )
        return [b["id"] for b in (response.data or [])]

    def sync_inventory_mode(self, old_mode: str, new_mode: str) -> None:
        if old_mode == new_mode:
            return
            
        logger.info(f"Syncing inventory mode for {self._business_id} from {old_mode} to {new_mode}")
            
        if new_mode == "centralizado":
            # por_sucursal → centralizado
            # 1. Fetch all inventario_sucursal, aggregate by product
            inv_suc = (
                self._client.table("inventario_sucursal")
                .select("producto_id, stock_actual")
                .eq("negocio_id", self._business_id)
                .execute()
            )
            
            # 2. Aggregate stock across all branches
            stock_map: Dict[str, float] = {}
            for item in inv_suc.data or []:
                pid = item["producto_id"]
                stock_map[pid] = stock_map.get(pid, 0.0) + float(item.get("stock_actual") or 0.0)
                
            # 3. Update productos.stock_actual and inventario_negocio
            for pid, stock in stock_map.items():
                try:
                    self._client.table("productos").update({"stock_actual": stock}).eq("id", pid).execute()
                    payload = {
                        "negocio_id": self._business_id,
                        "producto_id": pid,
                        "stock_total": stock
                    }
                    self._client.table("inventario_negocio").upsert(
                        payload, on_conflict="negocio_id,producto_id"
                    ).execute()
                except Exception as e:
                    logger.error(f"Error updating stock for product {pid}: {e}")
                    
            # 4. Clear inventario_sucursal (no longer needed)
            if inv_suc.data:
                self._client.table("inventario_sucursal").delete().eq("negocio_id", self._business_id).execute()
                logger.info(f"Cleared inventario_sucursal for {self._business_id}")
                
        elif new_mode == "por_sucursal":
            # centralizado → por_sucursal
            main_branch_id = self._get_main_branch_id()
            if not main_branch_id:
                logger.warning(f"No active branches found for {self._business_id}, cannot sync inventory.")
                return
                
            # 1. Build stock source: prefer inventario_negocio, fallback to productos.stock_actual
            inv_neg = (
                self._client.table("inventario_negocio")
                .select("producto_id, stock_total")
                .eq("negocio_id", self._business_id)
                .execute()
            )
            
            stock_map: Dict[str, float] = {}
            if inv_neg.data:
                for item in inv_neg.data:
                    stock_map[item["producto_id"]] = float(item.get("stock_total") or 0.0)
            else:
                # Fallback: use productos.stock_actual
                logger.info(f"inventario_negocio empty for {self._business_id}, using productos.stock_actual as source")
                productos = (
                    self._client.table("productos")
                    .select("id, stock_actual")
                    .eq("negocio_id", self._business_id)
                    .execute()
                )
                for p in productos.data or []:
                    stock_map[p["id"]] = float(p.get("stock_actual") or 0.0)
            
            # 2. Upsert to inventario_sucursal for main branch (other branches get 0)
            all_branches = self._get_all_active_branch_ids()
            
            for pid, stock in stock_map.items():
                for branch_id in all_branches:
                    # Main branch gets the full stock, others get 0
                    branch_stock = stock if branch_id == main_branch_id else 0.0
                    payload = {
                        "negocio_id": self._business_id,
                        "sucursal_id": branch_id,
                        "producto_id": pid,
                        "stock_actual": branch_stock,
                    }
                    try:
                        self._client.table("inventario_sucursal").upsert(
                            payload, on_conflict="sucursal_id,producto_id"
                        ).execute()
                    except Exception as e:
                        logger.error(f"Error creating inventario_sucursal for product {pid}, branch {branch_id}: {e}")
            
            # 3. Zero out productos.stock_actual (inventory is now tracked per branch)
            for pid in stock_map:
                try:
                    self._client.table("productos").update({"stock_actual": 0}).eq("id", pid).execute()
                except Exception as e:
                    logger.error(f"Error zeroing stock_actual for product {pid}: {e}")
                    
            # 4. Clear inventario_negocio
            if inv_neg.data:
                self._client.table("inventario_negocio").delete().eq("negocio_id", self._business_id).execute()
            
            logger.info(
                f"Inventory synced to por_sucursal for {self._business_id}. "
                f"{len(stock_map)} products × {len(all_branches)} branches."
            )

    def sync_services_mode(self, old_mode: str, new_mode: str) -> None:
        if old_mode == new_mode:
            return
            
        logger.info(f"Syncing services mode for {self._business_id} from {old_mode} to {new_mode}")
            
        if new_mode == "por_sucursal":
            # centralizado → por_sucursal
            branches_resp = (
                self._client.table("sucursales")
                .select("id")
                .eq("negocio_id", self._business_id)
                .eq("activo", True)
                .execute()
            )
            branches = [b["id"] for b in branches_resp.data or []]
            
            if not branches:
                return
                
            servicios_resp = (
                self._client.table("servicios")
                .select("id, precio, activo")
                .eq("negocio_id", self._business_id)
                .execute()
            )
            
            for branch_id in branches:
                for svc in servicios_resp.data or []:
                    payload = {
                        "negocio_id": self._business_id,
                        "sucursal_id": branch_id,
                        "servicio_id": svc["id"],
                        "precio": svc.get("precio"),
                        "estado": "activo" if svc.get("activo") else "inactivo"
                    }
                    try:
                        self._client.table("servicio_sucursal").upsert(
                            payload, on_conflict="servicio_id,sucursal_id"
                        ).execute()
                    except Exception as e:
                        logger.error(f"Error copying service {svc.get('id')} to branch {branch_id}: {e}")
                        
        elif new_mode == "centralizado":
            # por_sucursal → centralizado
            # Update servicios from main branch data, but DO NOT delete from servicios
            main_branch_id = self._get_main_branch_id()
            if main_branch_id:
                serv_suc_resp = (
                    self._client.table("servicio_sucursal")
                    .select("servicio_id, precio, estado")
                    .eq("negocio_id", self._business_id)
                    .eq("sucursal_id", main_branch_id)
                    .execute()
                )
                
                for svc in serv_suc_resp.data or []:
                    update_payload = {}
                    if "precio" in svc and svc["precio"] is not None:
                        update_payload["precio"] = svc["precio"]
                    if "estado" in svc:
                        update_payload["activo"] = (svc["estado"] == "activo")
                        
                    if update_payload:
                        try:
                            self._client.table("servicios").update(update_payload).eq("id", svc["servicio_id"]).execute()
                        except Exception as e:
                            logger.error(f"Error updating service {svc.get('servicio_id')} from branch data: {e}")
                        
            # Delete all servicio_sucursal records
            self._client.table("servicio_sucursal").delete().eq("negocio_id", self._business_id).execute()
            logger.info(f"Cleared servicio_sucursal for {self._business_id}")

    def sync_product_catalog_mode(self, old_mode: str, new_mode: str) -> None:
        if old_mode == new_mode:
            return
            
        logger.info(f"Syncing product catalog mode for {self._business_id} from {old_mode} to {new_mode}")
            
        if new_mode == "por_sucursal":
            # compartido → por_sucursal
            branches_resp = (
                self._client.table("sucursales")
                .select("id")
                .eq("negocio_id", self._business_id)
                .eq("activo", True)
                .execute()
            )
            branches = [b["id"] for b in branches_resp.data or []]
            
            if not branches:
                return
                
            productos_resp = (
                self._client.table("productos")
                .select("id, precio_venta, codigo, activo")
                .eq("negocio_id", self._business_id)
                .execute()
            )
            
            for branch_id in branches:
                for prod in productos_resp.data or []:
                    payload = {
                        "negocio_id": self._business_id,
                        "sucursal_id": branch_id,
                        "producto_id": prod["id"],
                        "precio": prod.get("precio_venta"),
                        "sku_local": prod.get("codigo"),
                        "estado": "activo" if prod.get("activo") else "inactivo",
                        "visibilidad": True
                    }
                    try:
                        self._client.table("producto_sucursal").upsert(
                            payload, on_conflict="producto_id,sucursal_id"
                        ).execute()
                    except Exception as e:
                        logger.error(f"Error copying product {prod.get('id')} to branch {branch_id}: {e}")
                        
        elif new_mode == "compartido":
            # por_sucursal → compartido
            # Update productos from main branch data, but DO NOT delete from productos
            main_branch_id = self._get_main_branch_id()
            if main_branch_id:
                prod_suc_resp = (
                    self._client.table("producto_sucursal")
                    .select("producto_id, precio, sku_local, estado")
                    .eq("negocio_id", self._business_id)
                    .eq("sucursal_id", main_branch_id)
                    .execute()
                )
                
                for prod in prod_suc_resp.data or []:
                    update_payload = {}
                    if "precio" in prod and prod["precio"] is not None:
                        update_payload["precio_venta"] = prod["precio"]
                    if "sku_local" in prod and prod["sku_local"] is not None:
                        update_payload["codigo"] = prod["sku_local"]
                    if "estado" in prod:
                        update_payload["activo"] = (prod["estado"] == "activo")
                        
                    if update_payload:
                        try:
                            self._client.table("productos").update(update_payload).eq("id", prod["producto_id"]).execute()
                        except Exception as e:
                            logger.error(f"Error updating product {prod.get('producto_id')} from branch data: {e}")
                        
            # Delete all producto_sucursal records
            self._client.table("producto_sucursal").delete().eq("negocio_id", self._business_id).execute()
            logger.info(f"Cleared producto_sucursal for {self._business_id}")

