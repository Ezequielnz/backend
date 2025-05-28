from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid # Import uuid type

class BusinessBase(BaseModel):
    nombre: str
    # Eliminando campos que no están en la tabla negocios
    # descripcion: Optional[str] = None
    # direccion: Optional[str] = None
    # telefono: Optional[str] = None
    # email: Optional[str] = None
    # logo_url: Optional[str] = None
    creada_en: Optional[datetime] = None
    # Eliminando updated_at ya que no está en la tabla negocios
    # updated_at: Optional[datetime] = None

class BusinessCreate(BaseModel):
    nombre: str

# No necesitamos BusinessUpdate si no lo estamos usando para actualizar estos campos
# class BusinessUpdate(BaseModel):
#     nombre: Optional[str] = None

class Business(BusinessBase):
    id: uuid.UUID  # Usar tipo UUID
    creada_por: uuid.UUID # Añadir campo creada_por con tipo UUID
    rol: Optional[str] = None  # Campo adicional para el rol del usuario en el negocio, obtenido del join

    class Config:
        from_attributes = True
        # Opcional: permitir conversión de string a UUID si es necesario
        # json_encoders = {uuid.UUID: str}
        # json_decoders = {str: uuid.UUID} 