from typing import Optional, Union
from pydantic import BaseModel, EmailStr, Field

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

class UserLogin(BaseModel):
    # Cambiamos EmailStr a str para evitar el error 422 si envían un username
    # Usamos alias para aceptar tanto 'username' como 'email'
    email: str 
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