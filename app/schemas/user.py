from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from .usuario import UsuarioCreate, UsuarioUpdate, Usuario

# Aliases for English compatibility
UserCreate = UsuarioCreate
UserUpdate = UsuarioUpdate
UserResponse = Usuario

class Token(BaseModel):
    access_token: str
    token_type: str

class UserSignUp(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    nombre: str = Field(..., min_length=1)
    apellido: str = Field(..., min_length=1)

class SignUpResponse(BaseModel):
    message: str
    email: EmailStr
    requires_confirmation: bool
