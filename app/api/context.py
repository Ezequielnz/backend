from typing import Optional
from fastapi import Request, HTTPException, status
from pydantic import BaseModel
import jwt
from app.db.supabase_client import get_supabase_user_client


class BusinessBranchContext(BaseModel):
    user_id: str
    business_id: str
    branch_id: Optional[str] = None
    usuario_negocio_id: str


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
    usuario_negocio_id = user_business.data[0]["id"]

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

    # Set context into request.state for downstream usage
    setattr(request.state, "company_id", business_id)
    setattr(request.state, "branch_id", branch_id)

    return BusinessBranchContext(
        user_id=user_id,
        business_id=business_id,
        branch_id=branch_id,
        usuario_negocio_id=usuario_negocio_id,
    )