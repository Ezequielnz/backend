from typing import Optional
from pydantic import BaseModel

# Shared properties
class CategoriaBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None

# Properties to receive on item creation
class CategoriaCreate(CategoriaBase):
    pass

# Properties to receive on item update
class CategoriaUpdate(BaseModel): # Using BaseModel for partial updates
    nombre: Optional[str] = None
    descripcion: Optional[str] = None

# Properties to return to client
class Categoria(CategoriaBase):
    id: int

    class Config:
        from_attributes = True # Replaces orm_mode = True in Pydantic v2
        
# Properties stored in DB (if different from Categoria, not strictly needed if Categoria is sufficient)
# class CategoriaInDB(CategoriaBase):
#     id: int
#     # Potentially other DB specific fields
#
#     class Config:
#         from_attributes = True
