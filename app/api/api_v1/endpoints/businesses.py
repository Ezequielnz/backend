import hashlib
import json
import logging
from email.utils import format_datetime, parsedate_to_datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status, Request, Body, Response
from app.types.auth import User
from app.api.deps import get_current_user
from app.db.supabase_client import (
    get_supabase_user_client,
    get_supabase_anon_client,
    get_supabase_service_client,
)
from app.schemas.business import BusinessCreate, Business
from app.schemas.branch import Branch, BranchCreate, BranchUpdate
from app.schemas.invitacion import InvitacionCreate, InvitacionResponse, UsuarioNegocioUpdate
from supabase.lib.client_options import ClientOptions
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _build_etag(payload: Any) -> str:
    """Create a stable hash for the outgoing payload."""
    serialized = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _parse_iso_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        logger.debug("Unable to parse timestamp %s for cache headers", value)
        return None


def _select_last_modified(candidates: List[Optional[str]]) -> Optional[datetime]:
    parsed = [dt for dt in (_parse_iso_timestamp(value) for value in candidates) if dt]
    if not parsed:
        return None
    return max(parsed)


def _format_http_datetime(value: datetime) -> str:
    return format_datetime(value.astimezone(timezone.utc))


def _should_return_not_modified(
    request: Request, etag: str, last_modified: Optional[datetime]
) -> bool:
    inm = request.headers.get("if-none-match")
    if inm and inm.strip(' "W/') == etag:
        return True

    if last_modified:
        ims = request.headers.get("if-modified-since")
        if ims:
            try:
                ims_dt = parsedate_to_datetime(ims)
                if ims_dt.tzinfo is None:
                    ims_dt = ims_dt.replace(tzinfo=timezone.utc)
                if last_modified <= ims_dt:
                    return True
            except (TypeError, ValueError):
                logger.debug("Could not parse If-Modified-Since header %s", ims)
    return False


def _not_modified_response(etag: str, last_modified: Optional[datetime]) -> Response:
    headers = {"ETag": etag}
    if last_modified:
        headers["Last-Modified"] = _format_http_datetime(last_modified)
    return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)


def _set_cache_headers(response: Response, etag: str, last_modified: Optional[datetime]) -> None:
    response.headers["ETag"] = etag
    if last_modified:
        response.headers["Last-Modified"] = _format_http_datetime(last_modified)
    # Avoid aggressive caching on shared proxies but allow browser reuse per user
    response.headers.setdefault("Cache-Control", "private, must-revalidate")

router = APIRouter()

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_business(business_data: BusinessCreate, request: Request) -> Any:
    """Create a new business and assign the creating user as admin."""
    user = getattr(request.state, "user", None)
    # Asegurarse de que el usuario está autenticado (validado por middleware)
    if not user or not hasattr(user, 'id'): # Verificar que el objeto user tiene id
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated or user ID not available.",
        )

    # Usar el cliente Supabase base - la autenticación para RLS debe venir del token en la cabecera
    supabase = get_supabase_user_client(request.headers.get("Authorization", ""))

    try:
        # 1. Create the new business in the 'negocios' table
        logger.info(f"Attempting to create business: {business_data.nombre} for user {user.id}")
        # Incluir explícitamente el usuario_id como creada_por
        # Con RLS ENABLE INSERT WITH CHECK (true) + autenticación por token, esto debería pasar
        insert_data = {
            "nombre": business_data.nombre,
            "creada_por": str(user.id) # Asegurar que es string, Supabase espera UUID string
        }
        logger.info(f"Insert data: {insert_data}")

        try:
            business_response = supabase.table("negocios").insert([insert_data]).execute()
            
            if not business_response.data or len(business_response.data) == 0:
                logger.error("❌ Supabase INSERT returned no data")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Supabase did not return created business data."
                )
        except Exception as e:
            logger.error(f"❌ Supabase INSERT error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Supabase error creating business: {str(e)}"
            )
        # =============================================

        new_business = business_response.data[0]
        business_id = new_business.get("id")
        logger.info(f"✅ Business created with ID: {business_id}")

        # 2. Link the creating user to the business in 'usuarios_negocios' as admin
        logger.info(f"Linking user {user.id} to business {business_id} as admin.")
        
        # Verificar si hay registros huérfanos para este usuario
        logger.info(f"Checking for orphaned user-business relationships for user {user.id}")
        orphaned_check = supabase.table("usuarios_negocios") \
            .select("id, negocio_id") \
            .eq("usuario_id", user.id) \
            .execute()
        
        if orphaned_check.data:
            logger.info(f"Found {len(orphaned_check.data)} existing relationships for user {user.id}")
            for relationship in orphaned_check.data:
                # Verificar si el negocio asociado existe
                business_check = supabase.table("negocios") \
                    .select("id") \
                    .eq("id", relationship["negocio_id"]) \
                    .execute()
                
                if not business_check.data:
                    # El negocio no existe, eliminar la relación huérfana
                    logger.info(f"Removing orphaned relationship {relationship['id']} for non-existent business {relationship['negocio_id']}")
                    supabase.table("usuarios_negocios") \
                        .delete() \
                        .eq("id", relationship["id"]) \
                        .execute()
                else:
                    logger.info(f"Valid relationship found: user {user.id} -> business {relationship['negocio_id']}")
        else:
            logger.info(f"No existing relationships found for user {user.id}")
        
        try:
            try:
                user_business_link_response = supabase.table("usuarios_negocios").insert({
                    "usuario_id": str(user.id), # Asegurar que es string
                    "negocio_id": business_id,
                    "rol": "admin", # Assign admin role to the creator
                    "estado": "aceptado", # Creator is automatically accepted
                    "invitado_por": None # Explicitamente establecer a NULL si no hay un invitador
                }).execute()
                
                if not user_business_link_response.data or len(user_business_link_response.data) == 0:
                    logger.error("❌ Supabase INSERT usuarios_negocios returned no data")
                    # Rollback: eliminar el negocio creado
                    logger.info(f"Rolling back business creation for business_id: {business_id}")
                    supabase.table("negocios").delete().eq("id", business_id).execute()
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Error linking user to business - no data returned."
                    )
            except Exception as e:
                logger.error(f"❌ Supabase INSERT usuarios_negocios error: {str(e)}")
                # Rollback: eliminar el negocio creado
                logger.info(f"Rolling back business creation for business_id: {business_id}")
                supabase.table("negocios").delete().eq("id", business_id).execute()
                
                # Verificar si es un error de constraint único
                if "23505" in str(e):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Ya existe una relación para este usuario. Puede que tengas un negocio pendiente de configuración."
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Error linking user to business: {str(e)}"
                    )
                
        except HTTPException:
            raise  # Re-raise HTTPExceptions
        except Exception as e:
            logger.error(f"❌ Unexpected error linking user to business: {e}")
            # Rollback: eliminar el negocio creado
            logger.info(f"Rolling back business creation for business_id: {business_id}")
            supabase.table("negocios").delete().eq("id", business_id).execute()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error linking user to business: {str(e)}"
            )

        usuario_negocio_id = user_business_link_response.data[0].get("id")
        logger.info(f"✅ User {user.id} linked to business {business_id} with usuario_negocio_id: {usuario_negocio_id}")

        # 3. Optionally, set initial admin permissions in 'permisos_usuario_negocio'
        # Make this non-critical - if it fails, the business creation should still succeed
        try:
            initial_permissions = {
                "usuario_negocio_id": usuario_negocio_id,
                "acceso_total": True,
                "puede_ver_tareas": True,
                "puede_asignar_tareas": True,
                "puede_editar_tareas": True,
                "recurso": "general",
                "accion": "manage",
            }
            logger.info(f"Setting initial permissions for usuario_negocio_id: {usuario_negocio_id}")
            
            try:
                permissions_response = supabase.table("permisos_usuario_negocio").insert([initial_permissions]).execute()
                
                if permissions_response.data:
                    logger.info(f"✅ Initial permissions set successfully")
                else:
                    logger.warning("⚠️ Warning: Could not set initial permissions - No data returned")
            except Exception as e:
                logger.warning(f"⚠️ Warning: Could not set initial permissions: {str(e)}")
                
        except Exception as permissions_error:
            logger.error(f"⚠️ Warning: Error setting initial permissions (non-critical): {permissions_error}")
            # Continue with business creation even if permissions fail

        # 4. Create default tenant settings for the new business
        try:
            default_tenant_settings = {
                "tenant_id": business_id,
                "locale": "es-AR",
                "timezone": "America/Argentina/Buenos_Aires",
                "currency": "ARS",
                "sales_drop_threshold": 15,  # 15% threshold (Media sensitivity)
                "min_days_for_model": 30     # 30 days minimum for predictions
            }
            logger.info(f"Creating default tenant settings for business: {business_id}")
            
            try:
                tenant_settings_response = supabase.table("tenant_settings").insert([default_tenant_settings]).execute()
                
                if tenant_settings_response.data:
                    logger.info(f"✅ Default tenant settings created successfully")
                else:
                    logger.warning("⚠️ Warning: Could not create default tenant settings - No data returned")
            except Exception as e:
                logger.warning(f"⚠️ Warning: Could not create default tenant settings: {str(e)}")
                
        except Exception as tenant_settings_error:
            logger.error(f"⚠️ Warning: Error creating default tenant settings (non-critical): {tenant_settings_error}")
            # Continue with business creation even if tenant settings fail

        return {"message": "Business created successfully", "business_id": business_id}

    except HTTPException:
        raise # Re-lanzar HTTPExceptions que ya creamos
    except Exception as e:
        logger.error(f"❌ Error general creating business: {type(e).__name__} - {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating business: {str(e)}",
        )

@router.get("/", response_model=List[Business])
async def get_businesses(request: Request, response: Response) -> Any:
    """Return all businesses for the current user with cache-aware headers."""
    user = getattr(request.state, "user", None)
    if not user or not hasattr(user, "id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated.",
        )

    supabase = get_supabase_user_client(request.headers.get("Authorization", ""))

    try:
        logger.debug("Fetching business memberships for user %s", user.id)
        membership_response = (
            supabase.table("usuarios_negocios")
            .select("rol, negocio_id, estado")
            .eq("usuario_id", user.id)
            .eq("estado", "aceptado")
            .execute()
        )
    except Exception as exc:
        logger.error("Error getting business memberships for user %s: %s", user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting businesses",
        ) from exc

    membership_data = membership_response.data or []
    if not membership_data:
        logger.info("No business relationships found for user %s", user.id)
        return []

    business_ids = [
        item.get("negocio_id")
        for item in membership_data
        if item and item.get("negocio_id")
    ]

    if not business_ids:
        logger.info("Memberships without negocio_id for user %s", user.id)
        return []

    try:
        business_response = (
            supabase.table("negocios")
            .select("id, nombre, creada_por, creada_en, actualizado_en")
            .in_("id", business_ids)
            .execute()
        )
    except Exception as exc:
        logger.error("Error fetching business info for user %s: %s", user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting businesses",
        ) from exc

    business_map: Dict[str, Dict[str, Any]] = {}
    for negocio in business_response.data or []:
        negocio_id = negocio.get("id")
        if negocio_id:
            business_map[str(negocio_id)] = negocio

    businesses: List[Dict[str, Any]] = []
    last_modified_candidates: List[Optional[str]] = []

    for membership in membership_data:
        negocio_id = membership.get("negocio_id")
        negocio_data = business_map.get(str(negocio_id))
        if not negocio_data:
            logger.debug("Missing negocio data for membership %s", membership)
            continue

        last_modified_candidates.append(
            negocio_data.get("actualizado_en") or negocio_data.get("creada_en")
        )
        businesses.append(
            {
                "id": negocio_data.get("id"),
                "nombre": negocio_data.get("nombre"),
                "creada_por": negocio_data.get("creada_por"),
                "creada_en": negocio_data.get("creada_en"),
                "rol": membership.get("rol"),
            }
        )

    etag_payload = {"user_id": str(user.id), "businesses": businesses}
    etag = _build_etag(etag_payload)
    last_modified = _select_last_modified(last_modified_candidates)

    if _should_return_not_modified(request, etag, last_modified):
        logger.debug("Returning 304 for get_businesses user %s", user.id)
        return _not_modified_response(etag, last_modified)

    _set_cache_headers(response, etag, last_modified)
    logger.debug("Returning %d businesses for user %s", len(businesses), user.id)
    return businesses

@router.get("/{business_id}", response_model=Business)
async def get_business_by_id(business_id: str, request: Request) -> Any:
    """Get a specific business by ID for the current user."""
    user = getattr(request.state, "user", None)
    if not user or not hasattr(user, 'id'):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated.",
        )

    supabase = get_supabase_user_client(request.headers.get("Authorization", ""))

    try:
        # Verify that the user has access to this business through usuarios_negocios
        # and get the business data in one query
        # Solo seleccionar los campos que realmente existen en la tabla negocios
        response = supabase.table("usuarios_negocios") \
            .select("rol, negocios(id, nombre, creada_por, creada_en)") \
            .eq("usuario_id", user.id) \
            .eq("negocio_id", business_id) \
            .execute()

        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found or you don't have access to it.",
            )

        # Extract business data from the response
        user_business_data = response.data[0]
        negocio_data = user_business_data.get("negocios")
        
        if not negocio_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business data not found.",
            )

        # Construct the Business object with only the fields that exist
        business_obj = {
            "id": negocio_data.get("id"),
            "nombre": negocio_data.get("nombre"),
            "creada_por": negocio_data.get("creada_por"),
            "creada_en": negocio_data.get("creada_en"),
            "rol": user_business_data.get("rol"),
        }

        return business_obj

    except HTTPException:
        raise  # Re-raise HTTPExceptions
    except Exception as e:
        logger.error(f"Error getting business by ID: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting business: {str(e)}",
        )


@router.get("/{business_id}/branches", response_model=List[Branch])
async def get_business_branches(business_id: str, request: Request, response: Response) -> Any:
    """
    Retrieve the branches (sucursales) accessible to the current user for a business.
    Admins receive every active branch; other roles only receive their assignments.
    """

    user = getattr(request.state, "user", None)
    if not user or not hasattr(user, "id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated.",
        )

    supabase = get_supabase_user_client(request.headers.get("Authorization", ""))

    try:
        membership = (
            supabase.table("usuarios_negocios")
            .select("rol")
            .eq("usuario_id", user.id)
            .eq("negocio_id", business_id)
            .eq("estado", "aceptado")
            .limit(1)
            .execute()
        )
    except Exception as membership_error:
        logger.error(f"[branches] Error validating membership: {membership_error}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error validating business membership.",
        )

    if not membership.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este negocio.",
        )

    user_role = (membership.data[0] or {}).get("rol") or "empleado"

    try:
        branches: List[Dict[str, Any]] = []
        branch_last_modified: List[Optional[str]] = []

        if user_role == "admin":
            response = (
                supabase.table("sucursales")
                .select(
                    "id, negocio_id, nombre, codigo, direccion, activo, is_main, creado_en, actualizado_en"
                )
                .eq("negocio_id", business_id)
                .eq("activo", True)
                .execute()
            )
            branches = response.data or []
        else:
            assignments_response = (
                supabase.table("usuarios_sucursales")
                .select(
                    "sucursales(id, negocio_id, nombre, codigo, direccion, activo, is_main, creado_en, actualizado_en)"
                )
                .eq("usuario_id", user.id)
                .eq("negocio_id", business_id)
                .eq("activo", True)
                .execute()
            )

            for assignment in assignments_response.data or []:
                branch = assignment.get("sucursales")
                if branch and branch.get("activo", True):
                    branches.append(branch)

            # Fallback for legacy data without explicit assignments: main branch
            if not branches:
                fallback = (
                    supabase.table("sucursales")
                    .select(
                        "id, negocio_id, nombre, codigo, direccion, activo, is_main, creado_en, actualizado_en"
                    )
                    .eq("negocio_id", business_id)
                    .eq("is_main", True)
                    .limit(1)
                    .execute()
                )
                if fallback.data:
                    branches = fallback.data

        dedup: Dict[str, Dict[str, Any]] = {}
        for branch in branches:
            branch_id = branch.get("id")
            if branch_id:
                dedup[str(branch_id)] = branch
            branch_last_modified.append(
                branch.get("actualizado_en") or branch.get("creado_en")
            )

        ordered_branches = sorted(
            dedup.values(),
            key=lambda b: (
                0 if b.get("is_main") else 1,
                (b.get("nombre") or "").lower(),
            ),
        )

        etag_payload = {
            "business_id": business_id,
            "user_id": str(user.id),
            "branches": [
                {
                    "id": b.get("id"),
                    "codigo": b.get("codigo"),
                    "nombre": b.get("nombre"),
                    "updated": b.get("actualizado_en") or b.get("creado_en"),
                }
                for b in ordered_branches
            ],
        }
        etag = _build_etag(etag_payload)
        last_modified = _select_last_modified(branch_last_modified)

        if _should_return_not_modified(request, etag, last_modified):
            logger.debug(
                "Returning 304 for get_business_branches business=%s user=%s",
                business_id,
                user.id,
            )
            return _not_modified_response(etag, last_modified)

        _set_cache_headers(response, etag, last_modified)
        return ordered_branches

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[branches] Unexpected error fetching branches for business {business_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching branches for business.",
        )


@router.post("/{business_id}/branches", response_model=Branch, status_code=status.HTTP_201_CREATED)
async def create_business_branch(business_id: str, payload: BranchCreate, request: Request) -> Branch:
    """
    Create a new branch for the given business and sync catalog entries via DB triggers.
    Only owners/admins are allowed to perform this action.
    """
    user = getattr(request.state, "user", None)
    if not user or not hasattr(user, "id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated.",
        )

    user_supabase = get_supabase_user_client(request.headers.get("Authorization", ""))

    user_id_str = str(user.id)
    membership = (
        user_supabase.table("usuarios_negocios")
        .select("rol")
        .eq("usuario_id", user_id_str)
        .eq("negocio_id", business_id)
        .eq("estado", "aceptado")
        .limit(1)
        .execute()
    )
    if not membership.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este negocio.",
        )

    user_role = (membership.data[0] or {}).get("rol") or "empleado"
    if user_role not in {"owner", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los dueños o administradores pueden crear sucursales.",
        )

    branch_id = str(uuid4())
    insert_data = {
        "id": branch_id,
        "negocio_id": business_id,
        "nombre": payload.nombre,
        "codigo": payload.codigo,
        "direccion": payload.direccion,
        "activo": payload.activo,
        "is_main": payload.is_main,
    }

    service_supabase = get_supabase_service_client()

    try:
        response = (
            service_supabase.table("sucursales")
            .insert(insert_data)
            .execute()
        )
    except Exception as exc:
        logger.exception("Failed to create branch for business %s", business_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo crear la sucursal; intente nuevamente.",
        ) from exc

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase no devolvió la sucursal creada.",
        )

    branch_record = response.data[0]

    # Ensure the creator (owner/admin) has access to the new branch.
    try:
        assignment = (
            service_supabase.table("usuarios_sucursales")
            .select("id")
            .eq("usuario_id", user_id_str)
            .eq("negocio_id", business_id)
            .eq("sucursal_id", branch_record["id"])
            .limit(1)
            .execute()
        )
        if not assignment.data:
            service_supabase.table("usuarios_sucursales").insert(
                {
                    "usuario_id": str(user.id),
                    "negocio_id": business_id,
                    "sucursal_id": branch_record["id"],
                    "activo": True,
                }
            ).execute()
    except Exception as exc:
        logger.warning(
            "Unable to auto-assign branch %s to user %s: %s",
            branch_record.get("id"),
            user.id,
            exc,
        )

    return Branch(**branch_record)


@router.patch("/{business_id}/branches/{branch_id}", response_model=Branch)
async def update_business_branch(
    business_id: str,
    branch_id: UUID,
    payload: BranchUpdate,
    request: Request,
) -> Branch:
    """
    Update mutable fields for an existing branch (nombre, código, dirección, flags).
    """
    user = getattr(request.state, "user", None)
    if not user or not hasattr(user, "id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated.",
        )

    user_supabase = get_supabase_user_client(request.headers.get("Authorization", ""))
    user_id_str = str(user.id)
    membership = (
        user_supabase.table("usuarios_negocios")
        .select("rol")
        .eq("usuario_id", user_id_str)
        .eq("negocio_id", business_id)
        .eq("estado", "aceptado")
        .limit(1)
        .execute()
    )
    if not membership.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este negocio.",
        )

    user_role = (membership.data[0] or {}).get("rol") or "empleado"
    if user_role not in {"owner", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los dueños o administradores pueden modificar sucursales.",
        )

    branch_id_str = str(branch_id)
    update_data = payload.model_dump(exclude_unset=True)
    service_supabase = get_supabase_service_client()

    try:
        if update_data:
            update_response = (
                service_supabase.table("sucursales")
                .update(update_data)
                .eq("negocio_id", business_id)
                .eq("id", branch_id_str)
                .execute()
            )
            if update_response.data:
                return Branch(**update_response.data[0])
        # Either no updates provided or Supabase did not return the updated row.
        refreshed = (
            service_supabase.table("sucursales")
            .select(
                "id, negocio_id, nombre, codigo, direccion, activo, is_main, creado_en, actualizado_en"
            )
            .eq("negocio_id", business_id)
            .eq("id", branch_id_str)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.exception("Failed to update branch %s for business %s", branch_id_str, business_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo actualizar la sucursal.",
        ) from exc

    if not refreshed.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sucursal no encontrada.",
        )

    return Branch(**refreshed.data[0])

@router.delete("/{business_id}")
async def delete_business(business_id: str, request: Request) -> Any:
    """Delete a business and all its related data."""
    user = getattr(request.state, "user", None)
    if not user or not hasattr(user, 'id'):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated.",
        )

    supabase = get_supabase_user_client(request.headers.get("Authorization", ""))

    try:
        # First, verify that the user has admin access to this business
        response = supabase.table("usuarios_negocios") \
            .select("rol") \
            .eq("usuario_id", user.id) \
            .eq("negocio_id", business_id) \
            .execute()

        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found or you don't have access to it.",
            )

        user_role = response.data[0].get("rol")
        if user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can delete businesses.",
            )

        # Delete in the correct order to respect foreign key constraints
        # 1. First, get all usuario_negocio_ids for this business
        logger.info(f"Getting usuario_negocio relationships for business {business_id}")
        user_business_ids_response = supabase.table("usuarios_negocios") \
            .select("id") \
            .eq("negocio_id", business_id) \
            .execute()
        
        if user_business_ids_response.data:
            # Extract just the IDs
            usuario_negocio_ids = [item["id"] for item in user_business_ids_response.data]
            logger.info(f"Found usuario_negocio_ids: {usuario_negocio_ids}")
            
            # Delete permissions for these usuario_negocio relationships
            if usuario_negocio_ids:
                logger.info(f"Deleting permissions for usuario_negocio_ids: {usuario_negocio_ids}")
                permissions_response = supabase.table("permisos_usuario_negocio") \
                    .delete() \
                    .in_("usuario_negocio_id", usuario_negocio_ids) \
                    .execute()
                logger.info(f"Permissions deletion response: {permissions_response}")

        # 2. Delete user-business relationships
        logger.info(f"Deleting user-business relationships for business {business_id}")
        user_business_response = supabase.table("usuarios_negocios") \
            .delete() \
            .eq("negocio_id", business_id) \
            .execute()

        # 3. Delete products (if any)
        logger.info(f"Deleting products for business {business_id}")
        products_response = supabase.table("productos") \
            .delete() \
            .eq("negocio_id", business_id) \
            .execute()

        # 4. Delete categories (if any)
        logger.info(f"Deleting categories for business {business_id}")
        categories_response = supabase.table("categorias") \
            .delete() \
            .eq("negocio_id", business_id) \
            .execute()

        # 5. Finally, delete the business itself
        logger.info(f"Deleting business {business_id}")
        try:
            business_response = supabase.table("negocios") \
                .delete() \
                .eq("id", business_id) \
                .execute()
        except Exception as e:
            logger.error(f"❌ Supabase DELETE error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error deleting business: {str(e)}"
            )

        logger.info(f"✅ Business {business_id} deleted successfully")
        return {"message": "Business deleted successfully", "business_id": business_id}

    except HTTPException:
        raise  # Re-raise HTTPExceptions
    except Exception as e:
        logger.error(f"❌ Error deleting business: {type(e).__name__} - {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting business: {str(e)}",
        )

@router.get("/debug/{user_id}")
async def debug_user_businesses(user_id: str, request: Request) -> Any:
    """Debug endpoint to see all data for a user."""
    supabase = get_supabase_user_client(request.headers.get("Authorization", ""))
    
    try:
        logger.info(f"🐛 DEBUG: Checking data for user {user_id}")
        
        # 1. Check usuarios_negocios table
        user_business_response = supabase.table("usuarios_negocios") \
            .select("*") \
            .eq("usuario_id", user_id) \
            .execute()
        
        logger.info(f"🐛 usuarios_negocios records: {user_business_response.data}")
        
        # 2. Check negocios table
        all_businesses_response = supabase.table("negocios") \
            .select("*") \
            .eq("creada_por", user_id) \
            .execute()
        
        logger.info(f"🐛 negocios records: {all_businesses_response.data}")
        
        # 3. Check for orphaned records
        if user_business_response.data:
            business_ids = [item["negocio_id"] for item in user_business_response.data]
            logger.info(f"🐛 Business IDs from relationships: {business_ids}")
            
            for business_id in business_ids:
                business_check = supabase.table("negocios") \
                    .select("*") \
                    .eq("id", business_id) \
                    .execute()
                logger.info(f"🐛 Business {business_id} exists: {bool(business_check.data)}")
                if business_check.data:
                    logger.info(f"🐛 Business {business_id} data: {business_check.data[0]}")
        
        return {
            "user_id": user_id,
            "user_business_relationships": user_business_response.data,
            "businesses_created_by_user": all_businesses_response.data,
            "total_relationships": len(user_business_response.data or []),
            "total_businesses": len(all_businesses_response.data or [])
        }
        
    except Exception as e:
        logger.error(f"🐛 DEBUG ERROR: {e}")
        return {"error": str(e)}

@router.post("/repair/{user_id}")
async def repair_user_businesses(user_id: str, request: Request) -> Any:
    """Repair missing user-business relationships for orphaned businesses."""
    supabase = get_supabase_user_client(request.headers.get("Authorization", ""))
    
    try:
        logger.info(f"🔧 REPAIR: Starting repair for user {user_id}")
        
        # 1. Get all businesses created by this user
        all_businesses_response = supabase.table("negocios") \
            .select("*") \
            .eq("creada_por", user_id) \
            .execute()
        
        if not all_businesses_response.data:
            return {"message": "No businesses found for user", "repaired": 0}
        
        # 2. Get existing relationships
        existing_relationships_response = supabase.table("usuarios_negocios") \
            .select("negocio_id") \
            .eq("usuario_id", user_id) \
            .execute()
        
        existing_business_ids = [item["negocio_id"] for item in existing_relationships_response.data or []]
        logger.info(f"🔧 Existing relationships for businesses: {existing_business_ids}")
        
        # 3. Find orphaned businesses (businesses without relationships)
        orphaned_businesses = []
        for business in all_businesses_response.data:
            if business["id"] not in existing_business_ids:
                orphaned_businesses.append(business)
        
        logger.info(f"🔧 Found {len(orphaned_businesses)} orphaned businesses")
        
        # 4. Create missing relationships
        repaired_count = 0
        for business in orphaned_businesses:
            logger.info(f"🔧 Creating relationship for business {business['id']} ({business['nombre']})")
            
            try:
                relationship_response = supabase.table("usuarios_negocios").insert({
                    "usuario_id": user_id,
                    "negocio_id": business["id"],
                    "rol": "admin",
                    "estado": "aceptado",
                    "invitado_por": None
                }).execute()
                
                if relationship_response.data:
                    logger.info(f"✅ Created relationship for business {business['id']}")
                    repaired_count += 1
                else:
                    logger.error(f"❌ Failed to create relationship for business {business['id']}")
                    
            except Exception as e:
                logger.error(f"❌ Error creating relationship for business {business['id']}: {e}")
        
        return {
            "message": f"Repair completed. {repaired_count} relationships created.",
            "user_id": user_id,
            "total_businesses": len(all_businesses_response.data),
            "orphaned_businesses_found": len(orphaned_businesses),
            "relationships_repaired": repaired_count
        }
        
    except Exception as e:
        logger.error(f"🔧 REPAIR ERROR: {e}")
        return {"error": str(e)}

@router.get("/{business_id}/usuarios-pendientes")
async def listar_usuarios_pendientes(business_id: str, request: Request) -> Any:
    """Listar usuarios pendientes de aprobación para un negocio (solo admin o creador)."""
    user = getattr(request.state, "user", None)
    if not user or not hasattr(user, 'id'):
        raise HTTPException(status_code=401, detail="User not authenticated.")
    
    supabase = get_supabase_user_client(request.headers.get("Authorization", ""))
    
    try:
        # Verificar que el usuario es admin del negocio O el creador del negocio
        admin_check = supabase.table("usuarios_negocios").select("rol").eq("usuario_id", user.id).eq("negocio_id", business_id).execute()
        
        # También verificar si es el creador del negocio
        negocio_check = supabase.table("negocios").select("creada_por").eq("id", business_id).execute()
        
        is_admin = admin_check.data and admin_check.data[0].get("rol") == "admin"
        is_creator = negocio_check.data and negocio_check.data[0].get("creada_por") == user.id
        
        if not is_admin and not is_creator:
            raise HTTPException(status_code=403, detail="Solo el admin o creador del negocio puede ver usuarios pendientes.")
        
        # Obtener usuarios pendientes
        pendientes = supabase.table("usuarios_negocios") \
            .select("id, usuario_id, estado, creada_en") \
            .eq("negocio_id", business_id) \
            .eq("estado", "pendiente") \
            .limit(20) \
            .execute()
        
        if not pendientes.data:
            return []
        
        # Obtener datos de usuarios en batch
        usuario_ids = [p["usuario_id"] for p in pendientes.data]
        usuarios_data = {}
        
        if usuario_ids:
            usuarios_batch = supabase.table("usuarios") \
                .select("id, nombre, apellido, email") \
                .in_("id", usuario_ids) \
                .execute()
            
            for usuario in usuarios_batch.data or []:
                usuarios_data[usuario["id"]] = usuario
        
        # Construir resultado
        result = []
        for pendiente in pendientes.data:
            pendiente_completo = pendiente.copy()
            pendiente_completo["usuario"] = usuarios_data.get(pendiente["usuario_id"], {
                "nombre": "", "apellido": "", "email": ""
            })
            result.append(pendiente_completo)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en listar_usuarios_pendientes: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.post("/{business_id}/usuarios-pendientes/{usuario_negocio_id}/aprobar")
async def aprobar_usuario_negocio(
    business_id: str, 
    usuario_negocio_id: str, 
    request: Request,
    permisos_data: dict = Body(default={})
) -> Any:
    """Aprobar usuario pendiente y configurar sus permisos por módulos."""
    try:
        logger.info(f"=== Iniciando aprobación de usuario ===")
        logger.info(f"Business ID: {business_id}")
        logger.info(f"Usuario Negocio ID: {usuario_negocio_id}")
        logger.info(f"Permisos data: {permisos_data}")
        
        user = getattr(request.state, "user", None)
        if not user or not hasattr(user, 'id'):
            raise HTTPException(status_code=401, detail="User not authenticated.")
        
        logger.info(f"Usuario autenticado: {user.id}")
        
        supabase = get_supabase_user_client(request.headers.get("Authorization", ""))
        
        # Verificar que el usuario es el creador del negocio (solo él puede aprobar)
        logger.info("Verificando permisos del creador del negocio...")
        negocio_check = supabase.table("negocios").select("creada_por").eq("id", business_id).execute()
        
        if not negocio_check.data:
            logger.error(f"❌ Negocio no encontrado: {business_id}")
            raise HTTPException(status_code=404, detail="Negocio no encontrado.")
            
        if negocio_check.data[0].get("creada_por") != user.id:
            logger.error(f"❌ Usuario {user.id} no es el creador del negocio. Creador: {negocio_check.data[0].get('creada_por')}")
            raise HTTPException(status_code=403, detail="Solo el creador del negocio puede aprobar usuarios.")
        
        logger.info("✅ Usuario autorizado para aprobar")
        
        # Verificar que el usuario está pendiente
        logger.info("Verificando usuario pendiente...")
        usuario_check = supabase.table("usuarios_negocios") \
            .select("id, usuario_id, estado") \
            .eq("id", usuario_negocio_id) \
            .eq("negocio_id", business_id) \
            .eq("estado", "pendiente") \
            .execute()
        
        if not usuario_check.data:
            logger.error(f"❌ Usuario pendiente no encontrado: {usuario_negocio_id}")
            # Verificar si el usuario ya está aprobado
            already_approved = supabase.table("usuarios_negocios") \
                .select("id, usuario_id, estado") \
                .eq("id", usuario_negocio_id) \
                .eq("negocio_id", business_id) \
                .execute()
            
            if already_approved.data and already_approved.data[0].get("estado") == "aceptado":
                logger.warning(f"⚠️ Usuario ya está aprobado, verificando permisos...")
                # Verificar si ya tiene permisos
                existing_permisos = supabase.table("permisos_usuario_negocio") \
                    .select("id") \
                    .eq("usuario_negocio_id", usuario_negocio_id) \
                    .execute()
                
                if existing_permisos.data:
                    logger.info(f"✅ Usuario ya tiene permisos configurados")
                    # Obtener datos del usuario para la respuesta
                    usuario_data = supabase.table("usuarios") \
                        .select("nombre, apellido, email") \
                        .eq("id", already_approved.data[0]["usuario_id"]) \
                        .execute()
                    
                    return {
                        "message": "Usuario ya estaba aprobado con permisos configurados",
                        "usuario": usuario_data.data[0] if usuario_data.data else {},
                        "permisos": existing_permisos.data[0] if existing_permisos.data else {}
                    }
                else:
                    logger.warning(f"⚠️ Usuario aprobado pero sin permisos, creando permisos...")
                    # Continuar con la creación de permisos para usuario ya aprobado
                    usuario_check = already_approved
            else:
                raise HTTPException(status_code=404, detail="Usuario pendiente no encontrado.")
        
        logger.info(f"✅ Usuario encontrado: {usuario_check.data[0]}")
        
        # Configurar permisos por módulos ANTES de aprobar
        logger.info("Configurando permisos...")
        permisos_config = {
            "usuario_negocio_id": usuario_negocio_id,
            "recurso": "general",
            "accion": "acceso",
            "acceso_total": permisos_data.get("acceso_total", False),
            
            # Permisos de productos
            "puede_ver_productos": permisos_data.get("puede_ver_productos", False),
            "puede_editar_productos": permisos_data.get("puede_editar_productos", False),
            "puede_eliminar_productos": permisos_data.get("puede_eliminar_productos", False),
            
            # Permisos de clientes
            "puede_ver_clientes": permisos_data.get("puede_ver_clientes", False),
            "puede_editar_clientes": permisos_data.get("puede_editar_clientes", False),
            "puede_eliminar_clientes": permisos_data.get("puede_eliminar_clientes", False),
            
            # Permisos de categorías
            "puede_ver_categorias": permisos_data.get("puede_ver_categorias", False),
            "puede_editar_categorias": permisos_data.get("puede_editar_categorias", False),
            "puede_eliminar_categorias": permisos_data.get("puede_eliminar_categorias", False),
            
            # Permisos de ventas
            "puede_ver_ventas": permisos_data.get("puede_ver_ventas", False),
            "puede_editar_ventas": permisos_data.get("puede_editar_ventas", False),
            
            # Permisos de stock
            "puede_ver_stock": permisos_data.get("puede_ver_stock", False),
            "puede_editar_stock": permisos_data.get("puede_editar_stock", False),
            
            # Permisos de facturación
            "puede_ver_facturacion": permisos_data.get("puede_ver_facturacion", False),
            "puede_editar_facturacion": permisos_data.get("puede_editar_facturacion", False),
            
            # Permisos de tareas (existentes)
            "puede_ver_tareas": permisos_data.get("puede_ver_tareas", False),
            "puede_asignar_tareas": permisos_data.get("puede_asignar_tareas", False),
            "puede_editar_tareas": permisos_data.get("puede_editar_tareas", False),
            
            "creado_en": datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"Configuración de permisos: {permisos_config}")
        
        # Verificar si ya existen permisos para evitar duplicados
        existing_permisos = supabase.table("permisos_usuario_negocio") \
            .select("id") \
            .eq("usuario_negocio_id", usuario_negocio_id) \
            .execute()
        
        if existing_permisos.data:
            logger.warning("⚠️ Ya existen permisos, actualizando...")
            # Actualizar permisos existentes
            permisos_response = supabase.table("permisos_usuario_negocio") \
                .update(permisos_config) \
                .eq("usuario_negocio_id", usuario_negocio_id) \
                .execute()
        else:
            logger.info("Creando nuevos permisos...")
            # Crear permisos nuevos
            permisos_response = supabase.table("permisos_usuario_negocio") \
                .insert(permisos_config) \
                .execute()
        
        # No need to check for .error - Supabase raises exceptions on errors
        
        logger.info("✅ Permisos configurados exitosamente")
        
        # Aprobar usuario DESPUÉS de configurar permisos (solo si está pendiente)
        if usuario_check.data[0].get("estado") == "pendiente":
            logger.info("Aprobando usuario...")
            approval_response = supabase.table("usuarios_negocios") \
                .update({"estado": "aceptado"}) \
                .eq("id", usuario_negocio_id) \
                .execute()
            
            # No need to check for .error - Supabase raises exceptions on errors
            
            logger.info("✅ Usuario aprobado exitosamente")
        else:
            logger.info("✅ Usuario ya estaba aprobado")
        
        # Obtener datos del usuario aprobado para la respuesta
        logger.info("Obteniendo datos del usuario...")
        usuario_data = supabase.table("usuarios") \
            .select("nombre, apellido, email") \
            .eq("id", usuario_check.data[0]["usuario_id"]) \
            .execute()
        
        # No need to check for .error - Supabase raises exceptions on errors
        
        logger.info("✅ Aprobación completada exitosamente")
        
        return {
            "message": "Usuario aprobado correctamente",
            "usuario": usuario_data.data[0] if usuario_data.data else {},
            "permisos": permisos_response.data[0] if permisos_response.data else {}
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error inesperado en aprobación: {type(e).__name__} - {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error interno del servidor: {str(e)}"
        )

@router.post("/{business_id}/usuarios-pendientes/{usuario_negocio_id}/rechazar")
async def rechazar_usuario_pendiente(business_id: str, usuario_negocio_id: str, request: Request) -> Any:
    """Rechazar usuario pendiente (solo admin)."""
    user = getattr(request.state, "user", None)
    if not user or not hasattr(user, 'id'):
        raise HTTPException(status_code=401, detail="User not authenticated.")
    supabase = get_supabase_user_client(request.headers.get("Authorization", ""))
    # Verificar que el usuario es admin del negocio
    admin_check = supabase.table("usuarios_negocios").select("rol").eq("usuario_id", user.id).eq("negocio_id", business_id).execute()
    if not admin_check.data or admin_check.data[0].get("rol") != "admin":
        raise HTTPException(status_code=403, detail="Solo el admin puede rechazar usuarios.")
    # Cambiar estado a rechazado en lugar de eliminar
    supabase.table("usuarios_negocios").update({"estado": "rechazado"}).eq("id", usuario_negocio_id).execute()
    return {"message": "Usuario rechazado", "usuario_negocio_id": usuario_negocio_id}

@router.get("/public/buscar-negocios")
async def buscar_negocios(nombre: str = "", id: str = "") -> Any:
    supabase = get_supabase_anon_client()
    query = supabase.table("negocios").select("id, nombre")
    if nombre:
        query = query.ilike("nombre", f"%{nombre}%")
    if id:
        query = query.eq("id", id)
    response = query.limit(20).execute()
    return response.data or []

@router.get("/{business_id}/notificaciones")
async def obtener_notificaciones_negocio(business_id: str, request: Request) -> Any:
    """Obtener notificaciones para el centro de notificaciones (usuarios pendientes, etc.)."""
    user = getattr(request.state, "user", None)
    if not user or not hasattr(user, 'id'):
        raise HTTPException(status_code=401, detail="User not authenticated.")
    supabase = get_supabase_user_client(request.headers.get("Authorization", ""))
    
    # Verificar que el usuario tiene acceso al negocio
    access_check = supabase.table("usuarios_negocios").select("rol").eq("usuario_id", user.id).eq("negocio_id", business_id).execute()
    if not access_check.data:
        raise HTTPException(status_code=403, detail="No tienes acceso a este negocio.")
    
    # Verificar que el usuario es el creador del negocio (solo él ve notificaciones de aprobación)
    negocio_check = supabase.table("negocios").select("creada_por").eq("id", business_id).execute()
    if not negocio_check.data or negocio_check.data[0].get("creada_por") != user.id:
        # Si no es el creador, devolver lista vacía (sin notificaciones de aprobación)
        return []
    
    notificaciones = []
    
    # Obtener usuarios pendientes (solo para el creador del negocio)
    pendientes = supabase.table("usuarios_negocios") \
        .select("id, usuario_id, creada_en") \
        .eq("negocio_id", business_id) \
        .eq("estado", "pendiente") \
        .execute()
    
    for pendiente in pendientes.data or []:
        # Obtener datos del usuario
        usuario_data = supabase.table("usuarios") \
            .select("nombre, apellido, email") \
            .eq("id", pendiente["usuario_id"]) \
            .execute()
        
        if usuario_data.data:
            usuario = usuario_data.data[0]
            notificaciones.append({
                "id": f"approval_{pendiente['id']}",
                "type": "approval_request",
                "title": "Solicitud de acceso pendiente",
                "message": f"{usuario.get('nombre', '')} {usuario.get('apellido', '')} ({usuario.get('email', '')}) solicita acceso al negocio",
                "time": pendiente.get("creada_en"),
                "data": {
                    "usuario_negocio_id": pendiente["id"],
                    "business_id": business_id,
                    "usuario_id": pendiente["usuario_id"]
                }
            })
    
    return notificaciones

@router.get("/{business_id}/usuarios")
async def listar_usuarios_negocio(business_id: str, request: Request) -> Any:
    """Listar todos los usuarios asociados al negocio con sus permisos."""
    user = getattr(request.state, "user", None)
    if not user or not hasattr(user, 'id'):
        raise HTTPException(status_code=401, detail="User not authenticated.")
    
    supabase = get_supabase_user_client(request.headers.get("Authorization", ""))
    
    try:
        # Verificar que el usuario tiene acceso al negocio
        access_check = supabase.table("usuarios_negocios").select("rol").eq("usuario_id", user.id).eq("negocio_id", business_id).execute()
        if not access_check.data:
            raise HTTPException(status_code=403, detail="No tienes acceso a este negocio.")
        
        # Obtener todos los usuarios del negocio con una sola consulta optimizada
        usuarios_response = supabase.table("usuarios_negocios") \
            .select("id, usuario_id, rol, estado, creada_en, invitado_por") \
            .eq("negocio_id", business_id) \
            .limit(50) \
            .execute()
        
        if not usuarios_response.data:
            return []
        
        # Obtener IDs de usuarios para consulta batch
        usuario_ids = [u["usuario_id"] for u in usuarios_response.data]
        usuario_negocio_ids = [u["id"] for u in usuarios_response.data]
        
        # Consulta batch para datos de usuarios
        usuarios_data = {}
        if usuario_ids:
            usuarios_batch = supabase.table("usuarios") \
                .select("id, nombre, apellido, email, ultimo_acceso") \
                .in_("id", usuario_ids) \
                .execute()
            
            for usuario in usuarios_batch.data or []:
                usuarios_data[usuario["id"]] = usuario
        
        # Consulta batch para permisos
        permisos_data = {}
        if usuario_negocio_ids:
            permisos_batch = supabase.table("permisos_usuario_negocio") \
                .select("*") \
                .in_("usuario_negocio_id", usuario_negocio_ids) \
                .execute()
            
            for permiso in permisos_batch.data or []:
                permisos_data[permiso["usuario_negocio_id"]] = permiso
        
        # Construir resultado
        result = []
        for usuario_negocio in usuarios_response.data:
            usuario_completo = {
                "id": usuario_negocio["id"],
                "usuario_id": usuario_negocio["usuario_id"],
                "rol": usuario_negocio["rol"],
                "estado": usuario_negocio["estado"],
                "creada_en": usuario_negocio["creada_en"],
                "invitado_por": usuario_negocio["invitado_por"],
                "usuario": usuarios_data.get(usuario_negocio["usuario_id"], {}),
                "permisos": permisos_data.get(usuario_negocio["id"], {})
            }
            result.append(usuario_completo)
        
        return result
        
    except Exception as e:
        logger.error(f"Error en listar_usuarios_negocio: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.put("/{business_id}/usuarios/{usuario_negocio_id}/permisos")
async def actualizar_permisos_usuario(
    business_id: str, 
    usuario_negocio_id: str, 
    request: Request,
    permisos_data: dict = Body(...)
) -> Any:
    """Actualizar permisos de un usuario del negocio (solo admin)."""
    user = getattr(request.state, "user", None)
    if not user or not hasattr(user, 'id'):
        raise HTTPException(status_code=401, detail="User not authenticated.")
    
    supabase = get_supabase_user_client(request.headers.get("Authorization", ""))
    
    # Verificar que el usuario es admin del negocio
    admin_check = supabase.table("usuarios_negocios").select("rol").eq("usuario_id", user.id).eq("negocio_id", business_id).execute()
    if not admin_check.data or admin_check.data[0].get("rol") != "admin":
        raise HTTPException(status_code=403, detail="Solo el admin puede modificar permisos.")
    
    # Verificar que el usuario_negocio_id pertenece al negocio
    usuario_check = supabase.table("usuarios_negocios").select("id").eq("id", usuario_negocio_id).eq("negocio_id", business_id).execute()
    if not usuario_check.data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado en este negocio.")
    
    # Actualizar o crear permisos
    existing_permisos = supabase.table("permisos_usuario_negocio") \
        .select("id") \
        .eq("usuario_negocio_id", usuario_negocio_id) \
        .execute()
    
    # Preparar datos de permisos con campos obligatorios
    permisos_update = {
        "usuario_negocio_id": usuario_negocio_id,
        "recurso": "general",  # Campo obligatorio
        "accion": "acceso",    # Campo obligatorio
        **permisos_data,
        "actualizado_en": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        if existing_permisos.data:
            # Actualizar permisos existentes
            response = supabase.table("permisos_usuario_negocio") \
                .update(permisos_update) \
                .eq("usuario_negocio_id", usuario_negocio_id) \
                .execute()
        else:
            # Crear nuevos permisos
            permisos_update["creado_en"] = datetime.now(timezone.utc).isoformat()
            response = supabase.table("permisos_usuario_negocio") \
                .insert(permisos_update) \
                .execute()
        
        # No need to check for .error - Supabase raises exceptions on errors
        
        return {"message": "Permisos actualizados correctamente", "permisos": response.data[0] if response.data else {}}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error inesperado actualizando permisos: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.delete("/{business_id}/usuarios/{usuario_negocio_id}")
async def remover_usuario_negocio(business_id: str, usuario_negocio_id: str, request: Request) -> Any:
    """Remover usuario del negocio (solo admin)."""
    user = getattr(request.state, "user", None)
    if not user or not hasattr(user, 'id'):
        raise HTTPException(status_code=401, detail="User not authenticated.")
    
    supabase = get_supabase_user_client(request.headers.get("Authorization", ""))
    
    # Verificar que el usuario es admin del negocio
    admin_check = supabase.table("usuarios_negocios").select("rol").eq("usuario_id", user.id).eq("negocio_id", business_id).execute()
    if not admin_check.data or admin_check.data[0].get("rol") != "admin":
        raise HTTPException(status_code=403, detail="Solo el admin puede remover usuarios.")
    
    # Verificar que el usuario_negocio_id pertenece al negocio
    usuario_check = supabase.table("usuarios_negocios").select("id, usuario_id").eq("id", usuario_negocio_id).eq("negocio_id", business_id).execute()
    if not usuario_check.data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado en este negocio.")
    
    # No permitir que el admin se remueva a sí mismo
    if usuario_check.data[0]["usuario_id"] == user.id:
        raise HTTPException(status_code=400, detail="No puedes removerte a ti mismo del negocio.")
    
    # Eliminar permisos primero
    supabase.table("permisos_usuario_negocio").delete().eq("usuario_negocio_id", usuario_negocio_id).execute()
    
    # Eliminar relación usuario-negocio
    supabase.table("usuarios_negocios").delete().eq("id", usuario_negocio_id).execute()
    
    return {"message": "Usuario removido del negocio correctamente"}

# ==================== ENDPOINTS DE INVITACIONES ====================

@router.post("/{business_id}/invitaciones", response_model=InvitacionResponse)
async def invitar_usuario_negocio(
    business_id: str, 
    invitacion_data: InvitacionCreate, 
    request: Request
) -> Any:
    """
    Invitar un usuario a unirse al negocio (solo admin).
    Por ahora crea la invitación en la BD, en el futuro enviará email.
    """
    user = getattr(request.state, "user", None)
    if not user or not hasattr(user, 'id'):
        raise HTTPException(status_code=401, detail="User not authenticated.")
    
    supabase = get_supabase_user_client(request.headers.get("Authorization", ""))
    
    try:
        # Verificar que el usuario es admin del negocio
        admin_check = supabase.table("usuarios_negocios") \
            .select("rol") \
            .eq("usuario_id", user.id) \
            .eq("negocio_id", business_id) \
            .eq("estado", "aceptado") \
            .execute()
        
        if not admin_check.data or admin_check.data[0].get("rol") != "admin":
            raise HTTPException(status_code=403, detail="Solo los administradores pueden invitar usuarios.")
        
        # Obtener información del negocio
        negocio_info = supabase.table("negocios") \
            .select("nombre") \
            .eq("id", business_id) \
            .execute()
        
        if not negocio_info.data:
            raise HTTPException(status_code=404, detail="Negocio no encontrado.")
        
        negocio_nombre = negocio_info.data[0]["nombre"]
        
        # Verificar si el usuario ya existe
        usuario_existente = supabase.table("usuarios") \
            .select("id") \
            .eq("email", invitacion_data.email) \
            .execute()
        
        now = datetime.now(timezone.utc).isoformat()
        
        if usuario_existente.data:
            # Usuario ya existe, crear relación directamente
            usuario_id = usuario_existente.data[0]["id"]
            
            # Verificar si ya está asociado al negocio
            relacion_existente = supabase.table("usuarios_negocios") \
                .select("estado") \
                .eq("usuario_id", usuario_id) \
                .eq("negocio_id", business_id) \
                .execute()
            
            if relacion_existente.data:
                estado_actual = relacion_existente.data[0]["estado"]
                if estado_actual == "aceptado":
                    raise HTTPException(status_code=400, detail="El usuario ya es miembro de este negocio.")
                elif estado_actual == "pendiente":
                    raise HTTPException(status_code=400, detail="El usuario ya tiene una invitación pendiente.")
                elif estado_actual == "rechazado":
                    # Actualizar invitación rechazada a pendiente
                    supabase.table("usuarios_negocios") \
                        .update({
                            "estado": "pendiente", 
                            "rol": invitacion_data.rol,
                            "invitado_por": user.id,
                            "creada_en": now
                        }) \
                        .eq("usuario_id", usuario_id) \
                        .eq("negocio_id", business_id) \
                        .execute()
            else:
                # Crear nueva relación
                supabase.table("usuarios_negocios").insert({
                    "usuario_id": usuario_id,
                    "negocio_id": business_id,
                    "rol": invitacion_data.rol,
                    "estado": "pendiente",
                    "invitado_por": user.id,
                    "creada_en": now
                }).execute()
            
            message = f"Invitación enviada a {invitacion_data.email}. El usuario recibirá una notificación para aceptar."
        else:
            # Usuario no existe, crear invitación para registro futuro
            # TODO: En el futuro, aquí se enviará un email de invitación con link de registro
            message = f"Se ha preparado una invitación para {invitacion_data.email}. Cuando se registre, será automáticamente asociado al negocio."
            
            # Por ahora, podríamos crear una tabla de "invitaciones_pendientes" 
            # o simplemente retornar el mensaje
        
        return InvitacionResponse(
            message=message,
            email=invitacion_data.email,
            negocio_nombre=negocio_nombre,
            enviado=False  # True cuando implementemos el envío de emails
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error invitando usuario: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")


@router.put("/{business_id}/usuarios/{usuario_negocio_id}/estado")
async def actualizar_estado_usuario_negocio(
    business_id: str,
    usuario_negocio_id: str,
    estado_data: UsuarioNegocioUpdate,
    request: Request
) -> Any:
    """
    Actualizar el estado de un usuario en el negocio (aceptar/rechazar invitación).
    Puede ser usado por el propio usuario para aceptar/rechazar o por admin para cambiar estados.
    """
    user = getattr(request.state, "user", None)
    if not user or not hasattr(user, 'id'):
        raise HTTPException(status_code=401, detail="User not authenticated.")
    
    supabase = get_supabase_user_client(request.headers.get("Authorization", ""))
    
    try:
        # Obtener información de la relación usuario-negocio
        relacion_info = supabase.table("usuarios_negocios") \
            .select("usuario_id, estado, rol") \
            .eq("id", usuario_negocio_id) \
            .eq("negocio_id", business_id) \
            .execute()
        
        if not relacion_info.data:
            raise HTTPException(status_code=404, detail="Relación usuario-negocio no encontrada.")
        
        relacion = relacion_info.data[0]
        
        # Verificar permisos
        es_el_mismo_usuario = relacion["usuario_id"] == user.id
        
        # Verificar si es admin del negocio
        es_admin = False
        if not es_el_mismo_usuario:
            admin_check = supabase.table("usuarios_negocios") \
                .select("rol") \
                .eq("usuario_id", user.id) \
                .eq("negocio_id", business_id) \
                .eq("estado", "aceptado") \
                .execute()
            
            es_admin = admin_check.data and admin_check.data[0].get("rol") == "admin"
        
        if not es_el_mismo_usuario and not es_admin:
            raise HTTPException(status_code=403, detail="No tienes permisos para actualizar este estado.")
        
        # Preparar datos de actualización
        update_data = {
            "estado": estado_data.estado,
            "actualizado_en": datetime.now(timezone.utc).isoformat()
        }
        
        # Solo admin puede cambiar rol
        if estado_data.rol and es_admin:
            update_data["rol"] = estado_data.rol
        
        # Actualizar estado
        response = supabase.table("usuarios_negocios") \
            .update(update_data) \
            .eq("id", usuario_negocio_id) \
            .execute()
        
        # No need to check for .error - Supabase raises exceptions on errors
        
        # Si se acepta la invitación, crear permisos básicos
        if estado_data.estado == "aceptado" and relacion["estado"] != "aceptado":
            try:
                permisos_basicos = {
                    "usuario_negocio_id": usuario_negocio_id,
                    "recurso": "general",
                    "accion": "acceso",
                    "acceso_total": False,
                    "puede_ver_productos": True,
                    "puede_ver_clientes": True,
                    "puede_ver_ventas": True,
                    "creado_en": datetime.now(timezone.utc).isoformat()
                }
                
                supabase.table("permisos_usuario_negocio") \
                    .insert(permisos_basicos) \
                    .execute()
                    
            except Exception as permisos_error:
                logger.error(f"⚠️ Warning: Error creando permisos básicos: {permisos_error}")
        
        return {
            "message": f"Estado actualizado a '{estado_data.estado}' correctamente",
            "estado": estado_data.estado,
            "usuario_negocio_id": usuario_negocio_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error actualizando estado: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")
