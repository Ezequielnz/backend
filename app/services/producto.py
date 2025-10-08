from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.producto import Producto
from app.types.producto import ProductoCreate, ProductoUpdate


def get(db: Session, producto_id: int) -> Optional[Producto]:
    return db.query(Producto).filter(Producto.id == producto_id).first()


def get_by_codigo(db: Session, codigo: str) -> Optional[Producto]:
    return db.query(Producto).filter(Producto.codigo == codigo).first()


def get_multi(
    db: Session, *, skip: int = 0, limit: int = 100, only_active: bool = True
) -> List[Producto]:
    query = db.query(Producto)
    if only_active:
        query = query.filter(Producto.activo == True)
    return query.offset(skip).limit(limit).all()


def create(db: Session, *, obj_in: ProductoCreate) -> Producto:
    db_obj = Producto(
        nombre=obj_in.nombre,
        descripcion=obj_in.descripcion,
        precio_compra=obj_in.precio_compra,
        precio_venta=obj_in.precio_venta,
        stock_actual=obj_in.stock_actual,
        stock_minimo=obj_in.stock_minimo,
        categoria_id=obj_in.categoria_id,
        codigo=obj_in.codigo,
        activo=obj_in.activo,
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


def update(
    db: Session, *, db_obj: Producto, obj_in: ProductoUpdate
) -> Producto:
    update_data = obj_in.model_dump(exclude_unset=True)
    for field in update_data:
        setattr(db_obj, field, update_data[field])
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


def remove(db: Session, *, producto_id: int) -> Producto:
    obj = db.query(Producto).get(producto_id)
    if obj is None:
        raise ValueError(f"Producto with id {producto_id} not found")
    db.delete(obj)
    db.commit()
    return obj