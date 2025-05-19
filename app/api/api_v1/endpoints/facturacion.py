from fastapi import APIRouter, HTTPException, status

router = APIRouter()

@router.get("/")
async def get_facturas():
    """
    Obtener listado de facturas
    """
    return {"message": "Listado de facturas"}

@router.post("/")
async def generar_factura():
    """
    Generar nueva factura AFIP
    """
    return {"message": "Factura generada correctamente"}

@router.get("/errores")
async def get_errores_facturacion():
    """
    Obtener panel de errores de facturación
    """
    return {"message": "Panel de errores de facturación"} 