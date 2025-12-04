from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class UsuarioBase(BaseModel):
    """Base schema for user data."""
    email: EmailStr
    nombre: str = Field(..., min_length=1, max_length=50)
    apellido: str = Field(..., min_length=1, max_length=50)
    is_active: bool = True
    is_superuser: bool = False
    onboarding_completed: bool = False

class UsuarioCreate(UsuarioBase):
    """Schema for creating a new user."""
    password: str = Field(..., min_length=8)

class UsuarioUpdate(BaseModel):
    """Schema for updating an existing user."""
    email: Optional[EmailStr] = None
    nombre: Optional[str] = Field(None, min_length=1, max_length=50)
    apellido: Optional[str] = Field(None, min_length=1, max_length=50)
    password: Optional[str] = Field(None, min_length=8)
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    onboarding_completed: Optional[bool] = None

class Usuario(UsuarioBase):
    """Schema for user response."""
    id: int
    fecha_creacion: datetime
    fecha_actualizacion: datetime

    class Config:
        from_attributes = True

class UsuarioInDB(Usuario):
    """Schema for user in database."""
    hashed_password: str