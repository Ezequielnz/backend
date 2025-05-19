from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from app import crud, schemas
from app.db.session import get_db

router = APIRouter()


@router.get("/", response_model=List[schemas.Producto])
def get_productos(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    only_active: bool = True,
) -> Any:
    """
    Obtener listado de productos en stock
    """
    productos = crud.producto.get_multi(
        db, skip=skip, limit=limit, only_active=only_active
    )
    return productos


@router.post("/", response_model=schemas.Producto)
def create_producto(
    *,
    db: Session = Depends(get_db),
    producto_in: schemas.ProductoCreate,
) -> Any:
    """
    Crear un nuevo producto
    """
    if producto_in.codigo:
        producto = crud.producto.get_by_codigo(db, codigo=producto_in.codigo)
        if producto:
            raise HTTPException(
                status_code=400,
                detail="Ya existe un producto con este código.",
            )
    producto = crud.producto.create(db, obj_in=producto_in)
    return producto


@router.get("/{producto_id}", response_model=schemas.Producto)
def get_producto(
    *,
    db: Session = Depends(get_db),
    producto_id: int,
) -> Any:
    """
    Obtener un producto por ID
    """
    producto = crud.producto.get(db, producto_id=producto_id)
    if not producto:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado",
        )
    return producto


@router.put("/{producto_id}", response_model=schemas.Producto)
def update_producto(
    *,
    db: Session = Depends(get_db),
    producto_id: int,
    producto_in: schemas.ProductoUpdate,
) -> Any:
    """
    Actualizar un producto
    """
    producto = crud.producto.get(db, producto_id=producto_id)
    if not producto:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado",
        )
    producto = crud.producto.update(db, db_obj=producto, obj_in=producto_in)
    return producto


@router.delete("/{producto_id}", response_model=schemas.Producto)
def delete_producto(
    *,
    db: Session = Depends(get_db),
    producto_id: int,
) -> Any:
    """
    Eliminar un producto
    """
    producto = crud.producto.get(db, producto_id=producto_id)
    if not producto:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado",
        )
    producto = crud.producto.remove(db, producto_id=producto_id)
    return producto


@router.post("/importar")
async def importar_productos(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Any:
    """
    Importar productos desde un archivo Excel
    """
    # Aquí iría la lógica para importar productos desde Excel
    # Por ahora devolvemos una respuesta básica
    return {"message": f"Archivo {file.filename} importado correctamente"} 