from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger(__name__)

class JSONErrorMiddleware(BaseHTTPMiddleware):
    """
    Middleware que garantiza que todos los errores de las rutas API 
    sean devueltos como JSON en lugar de HTML.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Solo procesar rutas de API
        if "/api/" not in request.url.path:
            return await call_next(request)
            
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            # Log del error
            logger.error(f"Error no manejado en ruta {request.url.path}: {str(e)}")
            
            # Devolver error en formato JSON
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Error interno del servidor", 
                    "message": str(e)
                }
            )
