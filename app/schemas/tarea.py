from typing import Optional, List
from pydantic import BaseModel, validator
from datetime import date, datetime

# Base properties for a task
class TareaBase(BaseModel):
    titulo: str
    descripcion: Optional[str] = None
    fecha_fin: Optional[date] = None # Maps to 'fecha_vencimiento' from requirements
    estado: str # E.g., "pendiente", "en_progreso", "completada"
    prioridad: Optional[str] = "normal" # Default priority

    @validator('estado')
    def estado_must_be_valid(cls, value):
        valid_estados = ["pendiente", "en progreso", "completada", "cancelada"] # Example states
        if value.lower() not in valid_estados:
            raise ValueError(f"Estado must be one of {valid_estados}")
        return value.lower()

    @validator('prioridad')
    def prioridad_must_be_valid(cls, value):
        if value is None: # Allow None if that's desired for optionality
            return value
        valid_prioridades = ["baja", "normal", "alta", "urgente"] # Example priorities
        if value.lower() not in valid_prioridades:
            raise ValueError(f"Prioridad must be one of {valid_prioridades}")
        return value.lower()

# Properties to receive on task creation
class TareaCreate(TareaBase):
    asignado_id: Optional[str] = None # UUID of the user/employee the task is assigned to (string)
    # creado_por_id will be set automatically by the server using current_user.id

# Properties to receive on task update
class TareaUpdate(BaseModel): # All fields are optional for partial updates
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    fecha_fin: Optional[date] = None
    estado: Optional[str] = None
    prioridad: Optional[str] = None
    asignado_id: Optional[str] = None # Allow changing assignee

    @validator('estado', pre=True, always=True)
    def estado_update_must_be_valid(cls, value):
        if value is None:
            return value
        valid_estados = ["pendiente", "en progreso", "completada", "cancelada"]
        if value.lower() not in valid_estados:
            raise ValueError(f"Estado must be one of {valid_estados}")
        return value.lower()

    @validator('prioridad', pre=True, always=True)
    def prioridad_update_must_be_valid(cls, value):
        if value is None:
            return value
        valid_prioridades = ["baja", "normal", "alta", "urgente"]
        if value.lower() not in valid_prioridades:
            raise ValueError(f"Prioridad must be one of {valid_prioridades}")
        return value.lower()

# Properties to return to client
class TareaResponse(TareaBase):
    id: int
    creado_por_id: str # UUID of the user who created the task (string)
    asignado_id: Optional[str] = None # UUID of the user assigned to the task (string)
    creado_en: datetime # Maps to 'fecha_creacion'
    actualizado_en: Optional[datetime] = None # Maps to 'fecha_actualizacion'

    # Optional: Include nested user details if needed in the future
    # asignado_a: Optional[UsuarioSchema] = None
    # creado_por: UsuarioSchema

    class Config:
        from_attributes = True # Replaces orm_mode = True in Pydantic v2

# For listing tasks, can include query parameters schema if complex
class TareaListParams(BaseModel):
    asignado_id: Optional[str] = None
    creado_por_id: Optional[str] = None
    estado: Optional[str] = None
    # For fecha_fin, more complex filtering (due_on, before, after, range) might be handled directly in endpoint params
    # For simplicity, let's assume a direct match or a range for fecha_fin if implemented
    fecha_fin_desde: Optional[date] = None
    fecha_fin_hasta: Optional[date] = None
    prioridad: Optional[str] = None
    
    # Add list of valid estados and prioridades for potential use in endpoint or docs
    VALID_ESTADOS: List[str] = ["pendiente", "en progreso", "completada", "cancelada"]
    VALID_PRIORIDADES: List[str] = ["baja", "normal", "alta", "urgente"]

    @validator('estado', pre=True, always=True)
    def list_estado_must_be_valid(cls, value):
        if value is None: return value
        if value.lower() not in cls.VALID_ESTADOS:
            raise ValueError(f"Estado must be one of {cls.VALID_ESTADOS}")
        return value.lower()

    @validator('prioridad', pre=True, always=True)
    def list_prioridad_must_be_valid(cls, value):
        if value is None: return value
        if value.lower() not in cls.VALID_PRIORIDADES:
            raise ValueError(f"Prioridad must be one of {cls.VALID_PRIORIDADES}")
        return value.lower()
