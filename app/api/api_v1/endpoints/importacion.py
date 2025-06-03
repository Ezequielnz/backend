from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import JSONResponse

from app.api.deps import get_current_user, UserData
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
    dependencies=[Depends(PermissionDependency("puede_editar_productos"))]
)
async def subir_archivo_excel(
    business_id: str,
    file: UploadFile = File(...),
    sheet_name: Optional[str] = Form(None),
    current_user: UserData = Depends(get_current_user)
):
    """
    Sube y procesa un archivo Excel para importación masiva de productos.
    
    Args:
        business_id: ID del negocio
        file: Archivo Excel a procesar
        sheet_name: Nombre de la hoja a procesar (opcional)
        current_user: Usuario actual
        
    Returns:
        Resultado del procesamiento inicial
    """
    try:
        # Validar tipo de archivo
        if not file.filename.endswith(('.xlsx', '.xls')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo debe ser un Excel (.xlsx o .xls)"
            )
        
        # Validar tamaño del archivo (máximo 10MB)
        file_content = await file.read()
        if len(file_content) > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo no puede ser mayor a 10MB"
            )
        
        # Procesar archivo
        service = ImportacionProductosService()
        resultado = await service.procesar_archivo_excel(
            file_content=file_content,
            negocio_id=business_id,
            usuario_id=current_user["id"],
            sheet_name=sheet_name
        )
        
        return resultado
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno del servidor: {str(e)}"
        )

@router.get("/resumen", response_model=ResumenImportacion,
    dependencies=[Depends(PermissionDependency("puede_ver_productos"))]
)
async def obtener_resumen_importacion(
    business_id: str,
    current_user: UserData = Depends(get_current_user)
):
    """
    Obtiene el resumen de la importación en curso.
    
    Args:
        business_id: ID del negocio
        current_user: Usuario actual
        
    Returns:
        Resumen de la importación
    """
    try:
        service = ImportacionProductosService()
        resumen = await service.obtener_resumen_importacion(
            negocio_id=business_id,
            usuario_id=current_user["id"]
        )
        
        return resumen
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno del servidor: {str(e)}"
        )

@router.get("/productos-temporales", response_model=List[ProductoImportacionTemporal],
    dependencies=[Depends(PermissionDependency("puede_ver_productos"))]
)
async def obtener_productos_temporales(
    business_id: str,
    estado: Optional[str] = None,
    current_user: UserData = Depends(get_current_user)
):
    """
    Obtiene los productos temporales de la importación en curso.
    
    Args:
        business_id: ID del negocio
        estado: Filtrar por estado (pendiente, validado, error)
        current_user: Usuario actual
        
    Returns:
        Lista de productos temporales
    """
    try:
        service = ImportacionProductosService()
        productos = await service.obtener_productos_temporales(
            negocio_id=business_id,
            usuario_id=current_user["id"],
            estado=estado
        )
        
        return productos
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno del servidor: {str(e)}"
        )

@router.put("/productos-temporales/{producto_id}", response_model=ProductoImportacionTemporal,
    dependencies=[Depends(PermissionDependency("puede_editar_productos"))]
)
async def actualizar_producto_temporal(
    business_id: str,
    producto_id: str,
    producto_update: ProductoImportacionUpdate,
    current_user: UserData = Depends(get_current_user)
):
    """
    Actualiza un producto temporal.
    
    Args:
        business_id: ID del negocio
        producto_id: ID del producto temporal
        producto_update: Datos a actualizar
        current_user: Usuario actual
        
    Returns:
        Producto temporal actualizado
    """
    try:
        service = ImportacionProductosService()
        
        # Convertir a diccionario excluyendo valores None
        datos_actualizacion = producto_update.model_dump(exclude_unset=True, exclude_none=True)
        
        producto_actualizado = await service.actualizar_producto_temporal(
            producto_id=producto_id,
            negocio_id=business_id,
            usuario_id=current_user["id"],
            datos_actualizacion=datos_actualizacion
        )
        
        return producto_actualizado
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno del servidor: {str(e)}"
        )

@router.post("/confirmar", response_model=ResultadoImportacionFinal,
    dependencies=[Depends(PermissionDependency("puede_editar_productos"))]
)
async def confirmar_importacion(
    business_id: str,
    confirmacion: ConfirmacionImportacion,
    current_user: UserData = Depends(get_current_user)
):
    """
    Confirma la importación y crea los productos definitivos.
    
    Args:
        business_id: ID del negocio
        confirmacion: Datos de confirmación
        current_user: Usuario actual
        
    Returns:
        Resultado de la importación final
    """
    try:
        service = ImportacionProductosService()
        resultado = await service.confirmar_importacion(
            negocio_id=business_id,
            usuario_id=current_user["id"],
            confirmacion=confirmacion
        )
        
        return resultado
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno del servidor: {str(e)}"
        )

@router.delete("/cancelar",
    dependencies=[Depends(PermissionDependency("puede_editar_productos"))]
)
async def cancelar_importacion(
    business_id: str,
    current_user: UserData = Depends(get_current_user)
):
    """
    Cancela la importación en curso eliminando los datos temporales.
    
    Args:
        business_id: ID del negocio
        current_user: Usuario actual
        
    Returns:
        Confirmación de cancelación
    """
    try:
        service = ImportacionProductosService()
        await service.cancelar_importacion(
            negocio_id=business_id,
            usuario_id=current_user["id"]
        )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Importación cancelada correctamente"}
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno del servidor: {str(e)}"
        )

@router.get("/hojas-excel")
async def obtener_hojas_excel(
    file: UploadFile = File(...),
    current_user: UserData = Depends(get_current_user)
):
    """
    Obtiene los nombres de las hojas de un archivo Excel.
    
    Args:
        file: Archivo Excel
        current_user: Usuario actual
        
    Returns:
        Lista de nombres de hojas
    """
    try:
        # Validar tipo de archivo
        if not file.filename.endswith(('.xlsx', '.xls')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo debe ser un Excel (.xlsx o .xls)"
            )
        
        file_content = await file.read()
        service = ImportacionProductosService()
        sheet_names = service.excel_processor.get_sheet_names(file_content)
        
        return {"sheet_names": sheet_names}
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno del servidor: {str(e)}"
        )

@router.delete("/limpiar-antiguos",
    dependencies=[Depends(PermissionDependency("puede_editar_productos"))]
)
async def limpiar_importaciones_antiguas(
    current_user: UserData = Depends(get_current_user)
):
    """
    Limpia importaciones temporales antiguas (más de 24 horas).
    Útil para mantenimiento manual.
    
    Args:
        current_user: Usuario actual
        
    Returns:
        Número de registros eliminados
    """
    try:
        service = ImportacionProductosService()
        registros_eliminados = await service.limpiar_importaciones_antiguas()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": f"Limpieza completada. {registros_eliminados} registros eliminados.",
                "registros_eliminados": registros_eliminados
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al limpiar datos antiguos: {str(e)}"
        ) 