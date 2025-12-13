from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from app.api import deps
from app.schemas.metodo_pago import MetodoPagoCreate, MetodoPagoUpdate, MetodoPagoResponse
from app.models.supabase_models import MetodoPago
from app.db.scoped_client import get_scoped_supabase_user_client
from app.db.supabase_client import get_supabase_anon_client
from app.dependencies import PermissionDependency
import datetime

router = APIRouter()

@router.get("/", response_model=List[MetodoPagoResponse])
async def read_payment_methods(
    business_id: str,
    request: Request,
    skip: int = 0,
    limit: int = 100,
    # Dependencies if needed, e.g. permission check?
    # Keeping it simple or adding "puede_ver_configuracion" if it exists.
    # For now, let's assume if they can access the business, they can see payment methods.
) -> Any:
    """
    Retrieve payment methods for the business.
    """
    token = request.headers.get("Authorization", "")
    supabase = (
        get_scoped_supabase_user_client(token, business_id)
        if token
        else get_supabase_anon_client()
    )
    
    try:
        response = supabase.table("metodos_pago").select("*").eq("negocio_id", business_id).execute()
        return response.data if response.data else []
    except Exception as e:
        print(f"Error fetching payment methods: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener métodos de pago: {str(e)}"
        )

@router.post("/", response_model=MetodoPagoResponse)
async def create_payment_method(
    business_id: str,
    metodo_in: MetodoPagoCreate,
    request: Request,
    # current_user: Any = Depends(deps.get_current_active_user),
) -> Any:
    """
    Create new payment method.
    """
    token = request.headers.get("Authorization", "")
    supabase = (
        get_scoped_supabase_user_client(token, business_id)
        if token
        else get_supabase_anon_client()
    )
    
    try:
        data = metodo_in.dict()
        data["negocio_id"] = business_id
        
        # Ensure default values
        if "descuento_porcentaje" not in data or data["descuento_porcentaje"] is None:
            data["descuento_porcentaje"] = 0
            
        data["creado_en"] = datetime.datetime.now().isoformat()
        data["actualizado_en"] = datetime.datetime.now().isoformat()
        
        response = supabase.table("metodos_pago").insert(data).execute()
        
        if not response.data:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error al crear método de pago."
            )
            
        return response.data[0]
        
    except Exception as e:
        print(f"Error creating payment method: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear método de pago: {str(e)}"
        )

@router.put("/{id}", response_model=MetodoPagoResponse)
async def update_payment_method(
    business_id: str,
    id: int,
    metodo_in: MetodoPagoUpdate,
    request: Request,
) -> Any:
    """
    Update payment method.
    """
    token = request.headers.get("Authorization", "")
    supabase = (
        get_scoped_supabase_user_client(token, business_id)
        if token
        else get_supabase_anon_client()
    )
    
    try:
        data = metodo_in.dict(exclude_unset=True)
        data["actualizado_en"] = datetime.datetime.now().isoformat()
        
        response = supabase.table("metodos_pago").update(data).eq("id", id).eq("negocio_id", business_id).execute()
        
        if not response.data:
             raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Método de pago no encontrado."
            )
            
        return response.data[0]
    except Exception as e:
        print(f"Error updating payment method: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar método de pago: {str(e)}"
        )

@router.delete("/{id}")
async def delete_payment_method(
    business_id: str,
    id: int,
    request: Request,
):
    """
    Delete payment method.
    """
    token = request.headers.get("Authorization", "")
    supabase = (
        get_scoped_supabase_user_client(token, business_id)
        if token
        else get_supabase_anon_client()
    )
    
    try:
        # Soft delete or hard delete?
        # Usually hard delete for configuration if not used, or soft if used.
        # For simplicity, hard delete for now, or just standard delete.
        # Supabase models usually have delete method.
        
        response = supabase.table("metodos_pago").delete().eq("id", id).eq("negocio_id", business_id).execute()
        
        # Check if deleted? Supabase delete returns the deleted row if successful (if select was implied or configured).
        # Assuming successful for now.
        
        return Response(status_code=status.HTTP_204_NO_CONTENT)
        
    except Exception as e:
        print(f"Error deleting payment method: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar método de pago: {str(e)}"
        )
