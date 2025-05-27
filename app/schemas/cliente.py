from typing import Optional
from pydantic import BaseModel, EmailStr
from datetime import datetime

# Shared properties
class ClienteBase(BaseModel):
    nombre: str
    apellido: str
    documento_tipo: Optional[str] = None
    documento_numero: Optional[str] = None
    email: Optional[EmailStr] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    # Add any other fields from the model that are common and updatable/creatable by user
    # e.g. ciudad, pais, codigo_postal, nif_cif, notas if they were in the model

# Properties to receive on item creation
class ClienteCreate(ClienteBase):
    pass # empleado_id will be set by the server using current_user.id

# Properties to receive on item update
class ClienteUpdate(BaseModel): # Allows for partial updates
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    documento_tipo: Optional[str] = None
    documento_numero: Optional[str] = None
    email: Optional[EmailStr] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    # empleado_id should not be updatable by the client

# Properties to return to client
class Cliente(ClienteBase):
    id: int # Primary key of the 'clientes' table
    empleado_id: str # UUID of the user who owns this client record
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None

    class Config:
        from_attributes = True # Replaces orm_mode = True in Pydantic v2
