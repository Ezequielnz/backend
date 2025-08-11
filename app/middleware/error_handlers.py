from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import HTMLResponse
from starlette.types import ASGIApp, Message
import logging
import re

logger = logging.getLogger(__name__)

class JSONErrorMiddleware(BaseHTTPMiddleware):
    """
    Middleware que garantiza que todos los errores y respuestas de las rutas API 
    sean devueltos como JSON en lugar de HTML.
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        # Patrón para detectar HTML
        self.html_pattern = re.compile(r'<!DOCTYPE|<html|<body', re.IGNORECASE)
    
    async def dispatch(self, request: Request, call_next):
        # Procesar todas las rutas de API y finanzas
        if "/api/" not in request.url.path and "/finanzas" not in request.url.path:
            return await call_next(request)
            
        try:
            # Capturar la respuesta
            response = await call_next(request)
            
            # Verificar si la respuesta es HTML cuando debería ser JSON
            content_type = response.headers.get("content-type", "")
            
            # Si la respuesta parece HTML pero la ruta es API o finanzas
            # Nota: Ya no excluimos el código 304
            if ("text/html" in content_type.lower() or 
                (content_type == "" and response.status_code != 204)):
                
                # Para respuestas de tipo StreamingResponse o respuestas que usan el event stream
                if hasattr(response, "body") and response.body is not None:
                    # Respuesta normal
                    body = response.body
                    
                    # Si el cuerpo parece HTML
                    try:
                        decoded_body = body.decode("utf-8", errors="ignore")
                        if self.html_pattern.search(decoded_body):
                            logger.error(f"Respuesta HTML detectada en ruta API: {request.url.path}")
                            
                            # Devolver error en formato JSON
                            # Convertir código 304 a 200 para asegurar compatibilidad con clientes
                            status_code = 200 if response.status_code == 304 else 500
                            
                            return JSONResponse(
                                status_code=status_code,
                                content={
                                    "detail": "Error de respuesta", 
                                    "message": "La API devolvió HTML en lugar de JSON",
                                    "original_status": response.status_code
                                }
                            )
                    except Exception as decode_error:
                        logger.error(f"Error al decodificar respuesta: {str(decode_error)}")
                
                # Si llegamos aquí, mantener la respuesta original
                return response
            
            # Si todo está bien, devolver la respuesta original
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
