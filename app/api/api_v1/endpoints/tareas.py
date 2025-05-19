from fastapi import APIRouter, HTTPException, status

router = APIRouter()

@router.get("/")
async def get_tareas():
    """
    Obtener listado de tareas
    """
    return {"message": "Listado de tareas"}

@router.post("/")
async def create_tarea():
    """
    Crear una nueva tarea
    """
    return {"message": "Tarea creada correctamente"}

@router.get("/calendario")
async def get_calendario_tareas():
    """
    Obtener vista de calendario de tareas
    """
    return {"message": "Vista de calendario de tareas"}

@router.get("/empleado/{empleado_id}")
async def get_tareas_empleado(empleado_id: int):
    """
    Obtener tareas asignadas a un empleado
    """
    return {"message": f"Tareas asignadas al empleado {empleado_id}"} 