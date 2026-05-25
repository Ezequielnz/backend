"""
context.py — Contexto de negocio/sucursal para endpoints
==========================================================
Versión desktop: ScopedSupabaseClient es un alias del NullClient del shim.
Toda la lógica de "scoping" vía RLS ha sido simplificada.
Será reemplazado en Fase 3 cuando los endpoints migren a SQLAlchemy ORM.
"""
from typing import Any, NamedTuple, Optional

import jwt
from fastapi import HTTPException, Request, status
from pydantic import BaseModel

from app.db.supabase_client import get_supabase_user_client, _NullClient

# En desktop, ScopedSupabaseClient = el NullClient del shim.
# Se mantiene el alias para que los endpoints que hacen
# `from app.api.context import ScopedClientContext` sigan importando.
ScopedSupabaseClient = _NullClient


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


async def BusinessBranchContextDep(
    request: Request,
    business_id: str,
    branch_id: Optional[str] = None,
) -> BusinessBranchContext:
    """
    Dependency para validar contexto de negocio.
    En modo desktop usa el shim — la lógica real de auth será Fase 3.
    """
    token = request.headers.get("Authorization", "")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization header missing")

    client = get_supabase_user_client(token)
    user_id = get_user_id_from_token(token)

    if not branch_id:
        header_branch = request.headers.get("X-Branch-Id") or request.headers.get("X-Sucursal-Id")
        if header_branch:
            branch_id = header_branch

    # Membership verification via shim (retorna [] — no bloquea el flujo en desktop)
    user_business = (
        client.table("usuarios_negocios")
        .select("id, negocio_id, estado, rol")
        .eq("usuario_id", user_id)
        .eq("negocio_id", business_id)
        .eq("estado", "aceptado")
        .limit(1)
        .execute()
    )
    # Shim retorna data=[] — en desktop usamos fallback: user_role=admin
    if user_business.data:
        business_record = user_business.data[0]
        usuario_negocio_id = business_record["id"]
        user_role = business_record.get("rol") or "admin"
    else:
        usuario_negocio_id = "local"
        user_role = "admin"  # desktop: usuario único siempre es admin

    setattr(request.state, "company_id", business_id)
    setattr(request.state, "branch_id", branch_id)
    setattr(request.state, "user_role", user_role)
    setattr(request.state, "branch_settings", None)

    return BusinessBranchContext(
        user_id=user_id,
        business_id=business_id,
        branch_id=branch_id,
        usuario_negocio_id=usuario_negocio_id,
        user_role=user_role,
        branch_settings=None,
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
    """Dependency que devuelve un NullClient + contexto validado de negocio."""
    token = _extract_authorization_token(request)
    context = await BusinessBranchContextDep(request, business_id)
    client = get_supabase_user_client(token)
    setattr(request.state, "scoped_supabase_client", client)
    return ScopedClientContext(client=client, context=context)


async def BranchScopedClientDep(
    request: Request,
    business_id: str,
    branch_id: str,
) -> ScopedClientContext:
    """Dependency que valida negocio + sucursal y devuelve NullClient + contexto."""
    token = _extract_authorization_token(request)
    context = await BusinessBranchContextDep(request, business_id, branch_id)
    client = get_supabase_user_client(token)
    setattr(request.state, "scoped_supabase_client", client)
    return ScopedClientContext(client=client, context=context)


def scoped_client_from_request(request: Request) -> ScopedSupabaseClient:
    """Helper para reutilizar el cliente ya inyectado por los Deps anteriores."""
    client = getattr(request.state, "scoped_supabase_client", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Scoped client not initialised for this request",
        )
    return client
