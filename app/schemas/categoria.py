from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class CategoriaBase(BaseModel):
    """Base schema for category data."""
    nombre: str = Field(..., min_length=1, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=500)

class CategoriaCreate(CategoriaBase):
    """Schema for creating a new category."""
    pass

class CategoriaUpdate(BaseModel):
    """Schema for updating a category."""
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=500)

class Categoria(CategoriaBase):
    """Schema for category response."""
    id: str

    class Config:
        from_attributes = True 