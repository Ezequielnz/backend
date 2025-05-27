from fastapi import APIRouter

# Import existing endpoint modules
from app.api.api_v1.endpoints import ventas, stock, facturacion, tareas, comunicacion, auth
# Import new endpoint modules for categories and products
from app.api.api_v1.endpoints import categorias as categorias_router
from app.api.api_v1.endpoints import productos as productos_router
# Import new endpoint module for clients
from app.api.api_v1.endpoints import clientes as clientes_router
# Import new endpoint module for reports
from app.api.api_v1.endpoints import reportes as reportes_router
# Import new endpoint modules for subscription system
from app.api.api_v1.endpoints import planes as planes_router
from app.api.api_v1.endpoints import suscripciones as suscripciones_router
from app.api.api_v1.endpoints import webhooks as webhooks_router
# Import new endpoint module for onboarding
from app.api.api_v1.endpoints import onboarding as onboarding_router

api_router = APIRouter()

# Existing routers
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(ventas.router, prefix="/ventas", tags=["ventas"])
api_router.include_router(stock.router, prefix="/stock", tags=["stock"]) # This existing /stock might conflict or be an older version.
api_router.include_router(facturacion.router, prefix="/facturacion", tags=["facturacion"])
api_router.include_router(tareas.router, prefix="/tareas", tags=["tareas"])
api_router.include_router(comunicacion.router, prefix="/comunicacion", tags=["comunicacion"]) 

# Add new routers for categories and products
api_router.include_router(categorias_router.router, prefix="/categorias", tags=["categorias"])
api_router.include_router(productos_router.router, prefix="/productos", tags=["productos"])
# Add new router for clients
api_router.include_router(clientes_router.router, prefix="/clientes", tags=["clientes"])
# Add new router for reports
api_router.include_router(reportes_router.router, prefix="/reportes", tags=["reportes"])

# Add new routers for subscription system
api_router.include_router(planes_router.router, prefix="/planes", tags=["planes"])
api_router.include_router(suscripciones_router.router, prefix="/suscripciones", tags=["suscripciones"])
api_router.include_router(webhooks_router.router, prefix="/webhooks", tags=["webhooks"])
# Add new router for onboarding
api_router.include_router(onboarding_router.router, prefix="/onboarding", tags=["onboarding"])

# Note on /stock vs /productos:
# The existing `stock.router` is at prefix "/stock".
# The new `productos_router.router` is at prefix "/productos".
# This is good as they are distinct. If the intention was to replace /stock,
# then the old /stock router inclusion should be removed.
# For now, both will exist.