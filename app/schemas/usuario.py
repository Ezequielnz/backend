from typing import List, Optional
from pydantic import BaseModel, EmailStr
from datetime import datetime


# Shared properties
class UsuarioBase(BaseModel):
    email: EmailStr
    nombre: str
    apellido: str
    rol: str
    permisos: Optional[List[str]] = []


# Properties to receive via API on creation
class UsuarioCreate(UsuarioBase):
    pass


# Properties to receive via API on update
class UsuarioUpdate(UsuarioBase):
    email: Optional[EmailStr] = None
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    rol: Optional[str] = None


# Properties shared by models stored in DB
class UsuarioInDBBase(UsuarioBase):
    id: int
    creado_en: Optional[datetime] = None
    ultimo_acceso: Optional[datetime] = None

    class Config:
        orm_mode = True


# Properties to return via API
class Usuario(UsuarioInDBBase):
    pass


# Properties stored in DB
class UsuarioInDB(UsuarioInDBBase):
    pass 