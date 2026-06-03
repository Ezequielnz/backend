from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from app.db.supabase_client import get_supabase_service_client

logger = logging.getLogger(__name__)

class SyncService:
    """
    Handles synchronization of data when business modes change
    (e.g., switching from centralizado to por_sucursal and vice versa).
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

    def sync_inventory_mode(self, old_mode: str, new_mode: str) -> None:
        if old_mode == new_mode:
            return
            
        logger.info(f"Syncing inventory mode for {self._business_id} from {old_mode} to {new_mode}")
            
        if new_mode == "centralizado":
            # por_sucursal -> centralizado
            # 1. Fetch all inventario_sucursal
            inv_suc = self._client.table("inventario_sucursal").select("producto_id, stock_actual").eq("negocio_id", self._business_id).execute()
            
            # 2. Aggregate
            stock_map: Dict[str, float] = {}
            for item in inv_suc.data or []:
                pid = item["producto_id"]
                stock_map[pid] = stock_map.get(pid, 0.0) + float(item.get("stock_actual") or 0.0)
                
            # 3. Update productos and inventario_negocio
            for pid, stock in stock_map.items():
                try:
                    self._client.table("productos").update({"stock_actual": stock}).eq("id", pid).execute()
                    payload = {
                        "negocio_id": self._business_id,
                        "producto_id": pid,
                        "stock_total": stock
                    }
                    self._client.table("inventario_negocio").upsert(payload, on_conflict="negocio_id,producto_id").execute()
                except Exception as e:
                    logger.error(f"Error updating stock for product {pid}: {e}")
                    
            # 4. Clear inventario_sucursal
            if inv_suc.data:
                self._client.table("inventario_sucursal").delete().eq("negocio_id", self._business_id).execute()
                
        elif new_mode == "por_sucursal":
            # centralizado -> por_sucursal
            main_branch_id = self._get_main_branch_id()
            if not main_branch_id:
                logger.warning(f"No active branches found for {self._business_id}, cannot sync inventory to por_sucursal.")
                return
                
            # 1. Fetch inventario_negocio
            inv_neg = self._client.table("inventario_negocio").select("producto_id, stock_total").eq("negocio_id", self._business_id).execute()
            
            # 2. Insert to inventario_sucursal for main branch
            for item in inv_neg.data or []:
                pid = item["producto_id"]
                stock = item["stock_total"]
                payload = {
                    "negocio_id": self._business_id,
                    "sucursal_id": main_branch_id,
                    "producto_id": pid,
                    "stock_actual": stock
                }
                self._client.table("inventario_sucursal").upsert(payload, on_conflict="sucursal_id,producto_id").execute()
                
            # 3. Clear inventario_negocio
            if inv_neg.data:
                self._client.table("inventario_negocio").delete().eq("negocio_id", self._business_id).execute()

    def sync_services_mode(self, old_mode: str, new_mode: str) -> None:
        if old_mode == new_mode:
            return
            
        logger.info(f"Syncing services mode for {self._business_id} from {old_mode} to {new_mode}")
            
        if new_mode == "por_sucursal":
            # centralizado -> por_sucursal
            branches_resp = self._client.table("sucursales").select("id").eq("negocio_id", self._business_id).eq("activo", True).execute()
            branches = [b["id"] for b in branches_resp.data or []]
            
            if not branches:
                return
                
            servicios_resp = self._client.table("servicios").select("*").eq("negocio_id", self._business_id).execute()
            
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
                        self._client.table("servicio_sucursal").upsert(payload, on_conflict="servicio_id,sucursal_id").execute()
                    except Exception as e:
                        logger.error(f"Error copying service {svc.get('nombre')} to branch {branch_id}: {e}")
                        
        elif new_mode == "centralizado":
            # por_sucursal -> centralizado
            main_branch_id = self._get_main_branch_id()
            if main_branch_id:
                serv_suc_resp = self._client.table("servicio_sucursal").select("*").eq("negocio_id", self._business_id).eq("sucursal_id", main_branch_id).execute()
                
                # We do NOT delete from "servicios" since it holds the master catalog.
                # We just update "precio" and "activo" based on main branch settings.
                for svc in serv_suc_resp.data or []:
                    update_payload = {}
                    if "precio" in svc:
                        update_payload["precio"] = svc["precio"]
                    if "estado" in svc:
                        update_payload["activo"] = (svc["estado"] == "activo")
                        
                    if update_payload:
                        try:
                            self._client.table("servicios").update(update_payload).eq("id", svc["servicio_id"]).execute()
                        except Exception as e:
                            logger.error(f"Error copying service config back to central: {e}")
                        
            # Delete all servicio_sucursal
            self._client.table("servicio_sucursal").delete().eq("negocio_id", self._business_id).execute()
