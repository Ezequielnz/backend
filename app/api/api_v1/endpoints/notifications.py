from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Body
from fastapi.responses import JSONResponse
import logging

from app.api.deps import get_current_user_from_request as get_current_user
from app.dependencies import PermissionDependency
from app.services.notification_service import NotificationConfigService, NotificationRuleType
from app.schemas.tenant_settings import RubroEnum

logger = logging.getLogger(__name__)
router = APIRouter()


async def validate_business_admin(business_id: str, user_id: str):
    """Validar que el usuario puede administrar el negocio"""
    from app.db.supabase_client import get_supabase_client
    supabase = get_supabase_client()
    
    # Verificar si es creador del negocio
    business_check = supabase.table("negocios").select("creada_por").eq("id", business_id).execute()
    if business_check.data and business_check.data[0]["creada_por"] == user_id:
        return True
    
    # Verificar si es admin o tiene acceso total
    user_business = supabase.table("usuarios_negocios").select("id, rol").eq("usuario_id", user_id).eq("negocio_id", business_id).eq("estado", "aceptado").execute()
    
    if not user_business.data:
        raise HTTPException(status_code=403, detail="No tienes acceso a este negocio")
    
    user_business_id = user_business.data[0]["id"]
    rol = user_business.data[0]["rol"]
    
    if rol == "admin":
        return True
    
    # Verificar acceso total
    permisos = supabase.table("permisos_usuario_negocio").select("acceso_total").eq("usuario_negocio_id", user_business_id).execute()
    
    if permisos.data and permisos.data[0]["acceso_total"]:
        return True
    
    raise HTTPException(status_code=403, detail="No tienes permisos de administrador para este negocio")


@router.post("/businesses/{business_id}/notifications/initialize")
async def initialize_business_notifications(
    business_id: str,
    rubro: RubroEnum = Body(..., description="Rubro del negocio"),
    preferences: Optional[Dict] = Body(None, description="Preferencias iniciales"),
    current_user = Depends(get_current_user)
):
    """
    Inicializar notificaciones para un negocio.
    CONTROL TOTAL desde FastAPI, sin triggers.
    """
    service = NotificationConfigService()
    
    # Validar que el usuario puede configurar el negocio
    await validate_business_admin(business_id, current_user.id)
    
    # Inicializar configuración
    result = await service.initialize_business_notifications(
        tenant_id=business_id,
        rubro=rubro.value,
        user_preferences=preferences
    )
    
    return JSONResponse(content={
        "success": True,
        "message": f"Notificaciones inicializadas para rubro '{rubro.value}'",
        "data": result
    })


@router.get("/businesses/{business_id}/notifications/rules")
async def get_notification_rules(
    business_id: str,
    include_inactive: bool = False,
    current_user = Depends(get_current_user),
    _: Any = Depends(PermissionDependency("configuracion", "ver"))
):
    """
    Obtener reglas efectivas del negocio.
    Combina templates + overrides automáticamente.
    """
    service = NotificationConfigService()
    
    logger.info(f"Calling get_effective_rules with business_id: {business_id}")

    # Cast the bound (possibly decorated) method to an explicit async callable
    # so the type-checker sees the correct signature (tenant_id: str) and stops
    # reporting the spurious "missing self" / "missing tenant_id" issue.
    from typing import Callable, Coroutine, Any, cast
    typed_get_effective: Callable[[str], Coroutine[Any, Any, list]] = cast(
        Callable[[str], Coroutine[Any, Any, list]],
        service.get_effective_rules
    )
    rules = await typed_get_effective(business_id)
    
    if not include_inactive:
        rules = [r for r in rules if r.is_active]
    
    # Convertir a dict para JSON serialization
    rules_data = []
    for rule in rules:
        rule_dict = {
            "rule_type": rule.rule_type.value,
            "condition_config": rule.condition_config,
            "parameters": rule.parameters,
            "is_active": rule.is_active,
            "version": rule.version
        }
        rules_data.append(rule_dict)
    
    return JSONResponse(content={
        "rules": rules_data,
        "total": len(rules_data),
        "active": len([r for r in rules_data if r["is_active"]])
    })


@router.patch("/businesses/{business_id}/notifications/rules/{rule_type}")
async def update_notification_rule(
    business_id: str,
    rule_type: NotificationRuleType,
    updates: Dict = Body(...),
    current_user = Depends(get_current_user),
    _: Any = Depends(PermissionDependency("configuracion", "editar"))
):
    """
    Actualizar regla específica con override personalizado.
    No modifica templates base.
    """
    service = NotificationConfigService()
    
    result = await service.update_rule_override(
        tenant_id=business_id,
        rule_type=rule_type,
        overrides=updates
    )
    
    return JSONResponse(content={
        "success": True,
        "message": f"Regla '{rule_type.value}' actualizada",
        "data": result
    })


@router.get("/businesses/{business_id}/notifications")
async def get_notifications(
    business_id: str,
    limit: int = 20,
    unread_only: bool = False,
    current_user = Depends(get_current_user)
):
    """Obtener notificaciones del negocio"""
    from app.db.supabase_client import get_supabase_client
    supabase = get_supabase_client()
    
    try:
        query = supabase.table("notifications").select("""
            id, title, message, metadata, severity, is_read, read_at, created_at,
            notification_templates(icon, color, priority)
        """).eq("tenant_id", business_id)
        
        if unread_only:
            query = query.eq("is_read", False)
        
        query = query.order("created_at", desc=True).limit(limit)
        
        result = query.execute()
        
        return JSONResponse(content={
            "notifications": result.data or [],
            "total": len(result.data) if result.data else 0
        })
        
    except Exception as e:
        logger.error(f"Error getting notifications for {business_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al obtener notificaciones")


@router.post("/businesses/{business_id}/notifications/{notification_id}/mark-read")
async def mark_notification_read(
    business_id: str,
    notification_id: str,
    current_user = Depends(get_current_user)
):
    """Marcar notificación como leída"""
    from app.db.supabase_client import get_supabase_client
    supabase = get_supabase_client()
    
    try:
        result = supabase.table("notifications").update({
            "is_read": True,
            "read_at": "now()"
        }).eq("id", notification_id).eq("tenant_id", business_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Notificación no encontrada")
        
        return JSONResponse(content={"success": True})
        
    except Exception as e:
        logger.error(f"Error marking notification as read: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al marcar notificación")


@router.get("/rubros")
async def get_available_rubros():
    """Obtener rubros disponibles para configuración"""
    service = NotificationConfigService()
    rubros = await service.get_available_rubros()
    
    return JSONResponse(content={
        "rubros": rubros
    })
