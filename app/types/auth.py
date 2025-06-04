from typing import Optional
from pydantic import BaseModel, EmailStr

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class UserBase(BaseModel):
    email: EmailStr
    nombre: str
    apellido: str

class UserSignUp(UserBase):
    password: str
    negocio_id: Optional[str] = None  # UUID del negocio existente
    nuevo_negocio_nombre: Optional[str] = None  # Nombre del nuevo negocio a crear

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class User(UserBase):
    id: str
    creado_en: str
    ultimo_acceso: str

    class Config:
        from_attributes = True

class SignUpResponse(BaseModel):
    message: str
    email: str
    requires_confirmation: bool = True 