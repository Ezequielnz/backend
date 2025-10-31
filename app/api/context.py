from typing import Any, NamedTuple, Optional

import jwt
from fastapi import HTTPException, Request, status
from pydantic import BaseModel

from app.db.scoped_client import ScopedSupabaseClient, get_scoped_supabase_user_client
from app.db.supabase_client import get_supabase_user_client


class BusinessBranchContext(BaseModel):
    user_id: str
    business_id: str
    branch_id: Optional[str] = None
    usuario_negocio_id: str
    user_role: str
    branch_settings: Optional[dict[str, Any]] = None


def get_user_id_from_token(token: str) -> str:
    try:
        if token.startswith("Bearer "):
            token = token[7:]
        decoded = jwt.decode(token, options={"verify_signature": False})
        user_id = decoded.get("sub")
        if not user_id:
            raise ValueError("sub not present")
        return user_id
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")


async def BusinessBranchContextDep(request: Request, business_id: str, branch_id: Optional[str] = None) -> BusinessBranchContext:
    token = request.headers.get("Authorization", "")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization header missing")
    client = get_supabase_user_client(token)
    user_id = get_user_id_from_token(token)

    # Allow branch to be provided via header when not in path/query.
    if not branch_id:
        header_branch = request.headers.get("X-Branch-Id") or request.headers.get("X-Sucursal-Id")
        if header_branch:
            branch_id = header_branch

    # Verify business membership
    user_business = (
        client.table("usuarios_negocios")
        .select("id, negocio_id, estado, rol")
        .eq("usuario_id", user_id)
        .eq("negocio_id", business_id)
        .eq("estado", "aceptado")
        .limit(1)
        .execute()
    )
    if not user_business.data:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not a member of this business")
    business_record = user_business.data[0]
    usuario_negocio_id = business_record["id"]
    user_role = business_record.get("rol") or "empleado"

    # If branch specified, verify assignment
    if branch_id:
        user_branch = (
            client.table("usuarios_sucursales")
            .select("id")
            .eq("usuario_id", user_id)
            .eq("negocio_id", business_id)
            .eq("sucursal_id", branch_id)
            .eq("activo", True)
            .limit(1)
            .execute()
        )
        if not user_branch.data:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not assigned to this branch")

    # Retrieve branch settings (negocio_configuracion)
    settings_response = (
        client.table("negocio_configuracion")
        .select(
            "negocio_id, inventario_modo, servicios_modo, catalogo_producto_modo, permite_transferencias, transferencia_auto_confirma, default_branch_id, metadata, created_at, updated_at"
        )
        .eq("negocio_id", business_id)
        .limit(1)
        .execute()
    )
    branch_settings = settings_response.data[0] if settings_response.data else None

    # Set context into request.state for downstream usage
    setattr(request.state, "company_id", business_id)
    setattr(request.state, "branch_id", branch_id)
    setattr(request.state, "user_role", user_role)
    setattr(request.state, "branch_settings", branch_settings)

    return BusinessBranchContext(
        user_id=user_id,
        business_id=business_id,
        branch_id=branch_id,
        usuario_negocio_id=usuario_negocio_id,
        user_role=user_role,
        branch_settings=branch_settings,
    )


class ScopedClientContext(NamedTuple):
    client: ScopedSupabaseClient
    context: BusinessBranchContext


def _extract_authorization_token(request: Request) -> str:
    token = request.headers.get("Authorization", "")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
        )
    return token


async def BusinessScopedClientDep(
    request: Request,
    business_id: str,
) -> ScopedClientContext:
    """
    Dependency that returns a scoped Supabase client plus the validated business context.
    """
    token = _extract_authorization_token(request)
    context = await BusinessBranchContextDep(request, business_id)
    client = get_scoped_supabase_user_client(token, context.business_id)
    setattr(request.state, "scoped_supabase_client", client)
    return ScopedClientContext(client=client, context=context)


async def BranchScopedClientDep(
    request: Request,
    business_id: str,
    branch_id: str,
) -> ScopedClientContext:
    """
    Dependency that validates business + branch membership and returns a scoped client.
    """
    token = _extract_authorization_token(request)
    context = await BusinessBranchContextDep(request, business_id, branch_id)
    client = get_scoped_supabase_user_client(token, context.business_id, context.branch_id)
    setattr(request.state, "scoped_supabase_client", client)
    return ScopedClientContext(client=client, context=context)


def scoped_client_from_request(request: Request) -> ScopedSupabaseClient:
    """
    Helper to reuse the scoped client set by BusinessScopedClientDep/BranchScopedClientDep.
    Raises an HTTP 500 if the dependency was not executed beforehand.
    """
    client = getattr(request.state, "scoped_supabase_client", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Scoped Supabase client not initialised for this request",
        )
    return client
