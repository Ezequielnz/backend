from fastapi import APIRouter, HTTPException, status

router = APIRouter()

@router.get("/")
async def get_ventas():
    """
    Obtener listado de ventas
    """
    return {"message": "Listado de ventas"}

@router.post("/")
async def create_venta():
    """
    Crear una nueva venta
    """
    return {"message": "Venta creada correctamente"}

@router.get("/reporte")
async def get_reporte_ventas():
    """
    Obtener reporte de ganancias
    """
    return {"message": "Reporte de ganancias"} 