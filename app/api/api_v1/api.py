from fastapi import APIRouter

from app.api.api_v1.endpoints import ventas, stock, facturacion, tareas, comunicacion, auth, productos, categorias, businesses

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(businesses.router, prefix="/businesses", tags=["businesses"])
api_router.include_router(ventas.router, prefix="/ventas", tags=["ventas"])
api_router.include_router(stock.router, prefix="/stock", tags=["stock"])
api_router.include_router(facturacion.router, prefix="/facturacion", tags=["facturacion"])
api_router.include_router(tareas.router, prefix="/tareas", tags=["tareas"])
api_router.include_router(comunicacion.router, prefix="/comunicacion", tags=["comunicacion"])
api_router.include_router(productos.router, prefix="/businesses/{business_id}/products", tags=["products"])
api_router.include_router(categorias.router, prefix="/businesses/{business_id}/categories", tags=["categories"]) 