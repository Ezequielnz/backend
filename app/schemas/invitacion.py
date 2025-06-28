from typing import Optional
from pydantic import BaseModel, EmailStr

class InvitacionCreate(BaseModel):
    """Esquema para crear una invitación a un negocio"""
    email: EmailStr
    rol: str = "empleado"  # empleado o admin
    mensaje_personalizado: Optional[str] = None

class InvitacionResponse(BaseModel):
    """Respuesta al crear una invitación"""
    message: str
    email: str
    negocio_nombre: str
    enviado: bool = False  # Por ahora False, True cuando implementemos email

class InvitacionAccept(BaseModel):
    """Esquema para aceptar una invitación"""
    token: str
    password: str
    nombre: str
    apellido: str

class UsuarioNegocioUpdate(BaseModel):
    """Esquema para actualizar el estado de un usuario en un negocio"""
    estado: str  # aceptado, rechazado, pendiente
    rol: Optional[str] = None  # empleado, admin 