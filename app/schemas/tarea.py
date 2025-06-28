from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class EstadoTarea(str, Enum):
    """Estados posibles de una tarea"""
    PENDIENTE = "pendiente"
    EN_PROGRESO = "en_progreso"
    COMPLETADA = "completada"
    CANCELADA = "cancelada"
    PAUSADA = "pausada"

class PrioridadTarea(str, Enum):
    """Prioridades posibles de una tarea"""
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"
    URGENTE = "urgente"

class TareaBase(BaseModel):
    """Esquema base para tareas"""
    titulo: str = Field(..., min_length=1, max_length=200, description="Título de la tarea")
    descripcion: Optional[str] = Field(None, max_length=1000, description="Descripción detallada de la tarea")
    fecha_inicio: Optional[datetime] = Field(None, description="Fecha y hora de inicio de la tarea")
    fecha_fin: Optional[datetime] = Field(None, description="Fecha y hora de finalización de la tarea")
    estado: EstadoTarea = Field(EstadoTarea.PENDIENTE, description="Estado actual de la tarea")
    prioridad: PrioridadTarea = Field(PrioridadTarea.MEDIA, description="Prioridad de la tarea")

class TareaCreate(TareaBase):
    """Esquema para crear una nueva tarea"""
    asignada_a_id: Optional[str] = Field(None, description="ID del usuario_negocio al que se asigna la tarea")

class TareaUpdate(BaseModel):
    """Esquema para actualizar una tarea existente"""
    titulo: Optional[str] = Field(None, min_length=1, max_length=200)
    descripcion: Optional[str] = Field(None, max_length=1000)
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    estado: Optional[EstadoTarea] = None
    prioridad: Optional[PrioridadTarea] = None
    asignada_a_id: Optional[str] = None

class TareaResponse(TareaBase):
    """Esquema de respuesta para tareas"""
    id: str
    asignada_a_id: Optional[str] = None
    creada_por_id: Optional[str] = None
    negocio_id: str
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None
    
    # Información adicional del usuario asignado
    asignada_a: Optional[dict] = None
    creada_por: Optional[dict] = None

    class Config:
        from_attributes = True

class TareaListResponse(BaseModel):
    """Respuesta para listado de tareas con paginación"""
    tareas: List[TareaResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int

class TareaFiltros(BaseModel):
    """Filtros para búsqueda de tareas"""
    estado: Optional[EstadoTarea] = None
    prioridad: Optional[PrioridadTarea] = None
    asignada_a_id: Optional[str] = None
    creada_por_id: Optional[str] = None
    fecha_inicio_desde: Optional[datetime] = None
    fecha_inicio_hasta: Optional[datetime] = None
    fecha_fin_desde: Optional[datetime] = None
    fecha_fin_hasta: Optional[datetime] = None
    busqueda: Optional[str] = Field(None, max_length=100, description="Búsqueda por título o descripción")

class TareaCalendario(BaseModel):
    """Esquema para vista de calendario de tareas"""
    id: str
    titulo: str
    descripcion: Optional[str] = None
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    estado: EstadoTarea
    prioridad: PrioridadTarea
    asignada_a: Optional[dict] = None
    color: Optional[str] = None  # Color para el calendario basado en prioridad/estado

class TareaEstadisticas(BaseModel):
    """Estadísticas de tareas para dashboard"""
    total_tareas: int
    pendientes: int
    en_progreso: int
    completadas: int
    vencidas: int
    por_prioridad: dict
    por_empleado: List[dict]

class TareaNotificacion(BaseModel):
    """Esquema para notificaciones de tareas"""
    tarea_id: str
    tipo: str  # "asignada", "vencida", "completada", "comentario"
    mensaje: str
    usuario_id: str
    leida: bool = False
    creada_en: datetime 