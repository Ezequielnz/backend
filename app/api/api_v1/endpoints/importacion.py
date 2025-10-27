from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import JSONResponse

from app.api.deps import get_current_user_from_request as get_current_user
from app.api.context import BusinessScopedClientDep, ScopedClientContext
from app.types.auth import User
from app.services.importacion_productos import ImportacionProductosService
from app.schemas.importacion import (
    ImportacionResultado,
    ResumenImportacion,
    ProductoImportacionTemporal,
    ProductoImportacionUpdate,
    ConfirmacionImportacion,
    ResultadoImportacionFinal
)
from app.dependencies import PermissionDependency

router = APIRouter()

@router.post("/upload", response_model=ImportacionResultado,
            dependencies=[Depends(PermissionDependency("productos", "create"))])
async def upload_excel(
    business_id: str,
    file: UploadFile = File(...),
    sheet_name: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
):
    """
    Subir y procesar archivo Excel para importación de productos.
    """
    # Validar tipo de archivo
    if not file.filename.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se permiten archivos Excel (.xlsx, .xls)"
        )
    
    # Validar tamaño del archivo (máximo 10MB)
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo es demasiado grande. Máximo 10MB permitido."
        )
    
    try:
        service = ImportacionProductosService(scoped.client)
        resultado = await service.procesar_archivo_excel(
            content,
            business_id,
            sheet_name
        )
        return resultado
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error procesando archivo: {str(e)}"
        )

@router.get("/sheets/{session_id}")
async def get_sheets(
    session_id: str,
    current_user: User = Depends(get_current_user),
    business_id: str,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
):
    """
    Obtener nombres de hojas del archivo Excel subido.
    """
    try:
        service = ImportacionProductosService(scoped.client)
        sheets = await service.obtener_hojas_excel(session_id, business_id)
        return {"sheets": sheets}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo hojas: {str(e)}"
        )

@router.get("/preview/{session_id}", response_model=ResumenImportacion)
async def get_preview(
    session_id: str,
    current_user: User = Depends(get_current_user),
    business_id: str,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
):
    """
    Obtener vista previa de los productos a importar.
    """
    try:
        service = ImportacionProductosService(scoped.client)
        preview = await service.obtener_preview(session_id, business_id)
        return preview
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo preview: {str(e)}"
        )

@router.post("/mapping/{session_id}")
async def update_mapping(
    session_id: str,
    mapping: dict,
    current_user: User = Depends(get_current_user),
    business_id: str,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
):
    """
    Actualizar el mapeo de columnas Excel a campos de producto.
    """
    try:
        service = ImportacionProductosService(scoped.client)
        resultado = await service.actualizar_mapeo(
            session_id, 
            business_id, 
            mapping
        )
        return resultado
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error actualizando mapeo: {str(e)}"
        )

@router.put("/products/{session_id}")
async def update_products(
    session_id: str,
    productos: List[ProductoImportacionUpdate],
    current_user: User = Depends(get_current_user),
    business_id: str,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
):
    """
    Actualizar productos antes de la importación final.
    """
    try:
        service = ImportacionProductosService(scoped.client)
        # Convert Pydantic models to plain dicts because the service expects List[Dict[str, Any]]
        productos_payload = [p.model_dump() for p in productos]
        resultado = await service.actualizar_productos_temporales(
            session_id,
            business_id,
            productos_payload
        )
        return resultado
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error actualizando productos: {str(e)}"
        )

@router.post("/confirm/{session_id}", response_model=ResultadoImportacionFinal)
async def confirm_import(
    session_id: str,
    confirmacion: ConfirmacionImportacion,
    current_user: User = Depends(get_current_user),
    business_id: str,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
):
    """
    Confirmar e importar productos definitivamente.
    """
    try:
        service = ImportacionProductosService(scoped.client)
        resultado = await service.confirmar_importacion(
            session_id,
            business_id,
            confirmacion
        )
        return resultado
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error confirmando importación: {str(e)}"
        )

@router.delete("/cancel/{session_id}")
async def cancel_import(
    session_id: str,
    current_user: User = Depends(get_current_user),
    business_id: str,
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
):
    """
    Cancelar proceso de importación.
    """
    try:
        service = ImportacionProductosService(scoped.client)
        await service.cancelar_importacion(session_id, business_id)
        return {"message": "Importación cancelada exitosamente"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error cancelando importación: {str(e)}"
        )

@router.get("/status")
async def get_import_status():
    """
    Obtener estado del sistema de importación.
    """
    return {
        "message": "Sistema de importación funcionando correctamente",
        "status": "active",
        "supported_formats": [".xlsx", ".xls"]
    } 


