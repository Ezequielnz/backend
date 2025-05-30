from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class CategoriaBase(BaseModel):
    """Base schema for category data."""
    nombre: str
    descripcion: Optional[str] = None

class CategoriaCreate(CategoriaBase):
    """Schema for creating a new category."""
    pass

class CategoriaUpdate(BaseModel):
    """Schema for updating a category."""
    nombre: Optional[str] = None
    descripcion: Optional[str] = None

class Categoria(CategoriaBase):
    """Schema for category response."""
    id: str
    negocio_id: str  # This will be included in responses
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True  # Para compatibilidad con SQLAlchemy/ORM 