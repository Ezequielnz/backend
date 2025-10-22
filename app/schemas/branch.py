from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class Branch(BaseModel):
    """
    Lightweight schema for sucursales (branches) exposed via the API.
    Only includes fields required by the frontend selector.
    """

    id: UUID
    negocio_id: UUID
    nombre: str
    codigo: Optional[str] = None
    direccion: Optional[str] = None
    activo: bool = True
    is_main: bool = False
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None

    class Config:
        from_attributes = True
