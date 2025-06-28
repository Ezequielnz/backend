from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from typing import Optional, List, Any
from datetime import datetime
import math

from app.dependencies import PermissionDependency
from app.api.deps import verify_basic_business_access
from app.db.supabase_client import get_supabase_client
from app.schemas.tarea import (
    TareaCreate, TareaUpdate, TareaResponse, TareaListResponse,
    TareaFiltros, TareaCalendario, TareaEstadisticas,
    EstadoTarea, PrioridadTarea
)

router = APIRouter()

# ==================== ENDPOINTS CRUD ====================

@router.get("/", response_model=TareaListResponse)
async def get_tareas(
    business_id: str,
    request: Request,
    pagina: int = Query(1, ge=1, description="Número de página"),
    por_pagina: int = Query(20, ge=1, le=100, description="Tareas por página"),
    estado: Optional[str] = Query(None, description="Filtrar por estado (separados por comas)"),
    prioridad: Optional[PrioridadTarea] = Query(None, description="Filtrar por prioridad"),
    asignada_a_id: Optional[str] = Query(None, description="Filtrar por usuario asignado"),
    creada_por_id: Optional[str] = Query(None, description="Filtrar por creador"),
    fecha_inicio_desde: Optional[datetime] = Query(None, description="Fecha inicio desde"),
    fecha_inicio_hasta: Optional[datetime] = Query(None, description="Fecha inicio hasta"),
    busqueda: Optional[str] = Query(None, description="Búsqueda en título/descripción")
) -> Any:
    """
    Obtener listado de tareas con filtros y paginación.
    Todos los usuarios del negocio pueden acceder, pero se filtran las tareas según el rol:
    - Admin/Acceso total: Ve todas las tareas
    - Usuario normal: Solo ve las tareas asignadas a él
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    supabase = get_supabase_client()
    
    try:
        # Verificar acceso básico al negocio
        business_access = await verify_basic_business_access(business_id, user)
        user_role = business_access.get("rol", "empleado")
        user_negocio_id = business_access.get("id")
        
        # Construir query base
        query = supabase.table("tareas").select("""
            *,
            asignada_a:usuarios_negocios!asignada_a_id(
                id,
                rol,
                usuario:usuarios!usuarios_negocios_usuario_id_fkey(nombre, apellido, email)
            ),
            creada_por:usuarios_negocios!creada_por_id(
                id,
                rol,
                usuario:usuarios!usuarios_negocios_usuario_id_fkey(nombre, apellido, email)
            )
        """).eq("negocio_id", business_id)
        
        # Filtrar tareas según el rol del usuario
        if user_role not in ["admin", "propietario"]:
            # Usuario normal: solo ve las tareas asignadas a él
            query = query.eq("asignada_a_id", user_negocio_id)
        
        # Aplicar filtros adicionales (solo si tienen valores válidos)
        if estado and estado.strip():
            # Manejar múltiples estados separados por comas
            estados = [e.strip() for e in estado.split(',') if e.strip()]
            if len(estados) == 1:
                query = query.eq("estado", estados[0])
            elif len(estados) > 1:
                # Usar operador 'in' para múltiples valores
                query = query.in_("estado", estados)
        if prioridad:
            query = query.eq("prioridad", prioridad.value)
        if asignada_a_id and asignada_a_id.strip():
            query = query.eq("asignada_a_id", asignada_a_id)
        if creada_por_id and creada_por_id.strip():
            query = query.eq("creada_por_id", creada_por_id)
        if fecha_inicio_desde:
            query = query.gte("fecha_inicio", fecha_inicio_desde.isoformat())
        if fecha_inicio_hasta:
            query = query.lte("fecha_inicio", fecha_inicio_hasta.isoformat())
        if busqueda and busqueda.strip():
            # Búsqueda en título y descripción
            query = query.or_(f"titulo.ilike.%{busqueda}%,descripcion.ilike.%{busqueda}%")
        
        # Contar total de registros con los mismos filtros
        count_query = supabase.table("tareas").select("id", count="exact").eq("negocio_id", business_id)
        
        # Aplicar el mismo filtro de rol para el conteo
        if user_role not in ["admin", "propietario"]:
            count_query = count_query.eq("asignada_a_id", user_negocio_id)
            
        if estado and estado.strip():
            # Manejar múltiples estados para el conteo
            estados = [e.strip() for e in estado.split(',') if e.strip()]
            if len(estados) == 1:
                count_query = count_query.eq("estado", estados[0])
            elif len(estados) > 1:
                count_query = count_query.in_("estado", estados)
        if prioridad:
            count_query = count_query.eq("prioridad", prioridad.value)
        if asignada_a_id and asignada_a_id.strip():
            count_query = count_query.eq("asignada_a_id", asignada_a_id)
        if creada_por_id and creada_por_id.strip():
            count_query = count_query.eq("creada_por_id", creada_por_id)
        if fecha_inicio_desde:
            count_query = count_query.gte("fecha_inicio", fecha_inicio_desde.isoformat())
        if fecha_inicio_hasta:
            count_query = count_query.lte("fecha_inicio", fecha_inicio_hasta.isoformat())
        if busqueda and busqueda.strip():
            count_query = count_query.or_(f"titulo.ilike.%{busqueda}%,descripcion.ilike.%{busqueda}%")
        
        count_response = count_query.execute()
        total = count_response.count if count_response.count is not None else 0
        
        # Aplicar paginación
        offset = (pagina - 1) * por_pagina
        query = query.order("creado_en", desc=True).range(offset, offset + por_pagina - 1)
        
        response = query.execute()
        tareas = response.data or []
        
        # Procesar datos de usuarios
        for tarea in tareas:
            if tarea.get("asignada_a") and tarea["asignada_a"].get("usuario"):
                usuario = tarea["asignada_a"]["usuario"]
                tarea["asignada_a"] = {
                    "id": tarea["asignada_a"]["id"],
                    "nombre": usuario["nombre"],
                    "apellido": usuario["apellido"],
                    "email": usuario["email"]
                }
            
            if tarea.get("creada_por") and tarea["creada_por"].get("usuario"):
                usuario = tarea["creada_por"]["usuario"]
                tarea["creada_por"] = {
                    "id": tarea["creada_por"]["id"],
                    "nombre": usuario["nombre"],
                    "apellido": usuario["apellido"],
                    "email": usuario["email"]
                }
        
        total_paginas = math.ceil(total / por_pagina)
        
        return TareaListResponse(
            tareas=tareas,
            total=total,
            pagina=pagina,
            por_pagina=por_pagina,
            total_paginas=total_paginas
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error al obtener tareas: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

@router.post("/", response_model=TareaResponse)
async def create_tarea(
    business_id: str,
    tarea_data: TareaCreate,
    request: Request,
    _: Any = Depends(PermissionDependency("tareas", "asignar"))
) -> Any:
    """
    Crear una nueva tarea.
    Requiere permiso 'puede_asignar_tareas'.
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    print(f"🔍 DEBUG - Datos recibidos en endpoint:")
    print(f"  business_id: {business_id}")
    print(f"  user.id: {user.id}")
    print(f"  tarea_data: {tarea_data.model_dump()}")
    
    supabase = get_supabase_client()
    
    try:
        # Obtener usuario_negocio_id del creador
        creator_response = supabase.table("usuarios_negocios").select("id").eq(
            "usuario_id", user.id
        ).eq("negocio_id", business_id).eq("estado", "aceptado").execute()
        
        if not creator_response.data:
            raise HTTPException(status_code=403, detail="No tienes acceso a este negocio")
        
        creada_por_id = creator_response.data[0]["id"]
        
        # Validar que el usuario asignado pertenezca al negocio (si se especifica)
        if tarea_data.asignada_a_id:
            assigned_response = supabase.table("usuarios_negocios").select("id").eq(
                "id", tarea_data.asignada_a_id
            ).eq("negocio_id", business_id).eq("estado", "aceptado").execute()
            
            if not assigned_response.data:
                raise HTTPException(
                    status_code=400, 
                    detail="El usuario asignado no pertenece a este negocio"
                )
        
        # Crear la tarea
        now = datetime.now().isoformat()
        # Usar mode='json' para convertir automáticamente datetime y enums
        tarea_dict = tarea_data.model_dump(mode='json')
        
        # Asegurar que asignada_a_id sea explícitamente NULL si no se proporciona
        # para evitar que se use el valor por defecto gen_random_uuid() de la tabla
        if not tarea_dict.get("asignada_a_id"):
            tarea_dict["asignada_a_id"] = None
            
        tarea_dict.update({
            "negocio_id": business_id,
            "creada_por_id": creada_por_id,
            "creado_en": now,
            "actualizado_en": now
        })
        
        print(f"🔍 DEBUG - Datos a insertar en Supabase:")
        print(f"  tarea_dict: {tarea_dict}")
        print(f"  tipos: {[(k, type(v).__name__) for k, v in tarea_dict.items()]}")
        
        response = supabase.table("tareas").insert(tarea_dict).execute()
        
        print(f"🔍 DEBUG - Respuesta de Supabase:")
        print(f"  response.data: {response.data}")
        print(f"  response.count: {response.count}")
        
        if not response.data:
            raise HTTPException(status_code=500, detail="Error al crear la tarea")
        
        tarea_creada = response.data[0]
        
        # Obtener la tarea con información de usuarios
        tarea_completa = supabase.table("tareas").select("""
            *,
            asignada_a:usuarios_negocios!asignada_a_id(
                id,
                rol,
                usuario:usuarios!usuarios_negocios_usuario_id_fkey(nombre, apellido, email)
            ),
            creada_por:usuarios_negocios!creada_por_id(
                id,
                rol,
                usuario:usuarios!usuarios_negocios_usuario_id_fkey(nombre, apellido, email)
            )
        """).eq("id", tarea_creada["id"]).execute()
        
        if tarea_completa.data:
            tarea = tarea_completa.data[0]
            
            # Procesar datos de usuarios
            if tarea.get("asignada_a") and tarea["asignada_a"].get("usuario"):
                usuario = tarea["asignada_a"]["usuario"]
                tarea["asignada_a"] = {
                    "id": tarea["asignada_a"]["id"],
                    "nombre": usuario["nombre"],
                    "apellido": usuario["apellido"],
                    "email": usuario["email"]
                }
            
            if tarea.get("creada_por") and tarea["creada_por"].get("usuario"):
                usuario = tarea["creada_por"]["usuario"]
                tarea["creada_por"] = {
                    "id": tarea["creada_por"]["id"],
                    "nombre": usuario["nombre"],
                    "apellido": usuario["apellido"],
                    "email": usuario["email"]
                }
            
            return TareaResponse(**tarea)
        
        return TareaResponse(**tarea_creada)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error al crear tarea: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

@router.get("/calendario", response_model=List[TareaCalendario])
async def get_calendario_tareas(
    business_id: str,
    request: Request,
    fecha_inicio: Optional[datetime] = Query(None, description="Fecha inicio del rango"),
    fecha_fin: Optional[datetime] = Query(None, description="Fecha fin del rango"),
    _: Any = Depends(PermissionDependency("tareas", "ver"))
) -> Any:
    """
    Obtener tareas para vista de calendario.
    Requiere permiso 'puede_ver_tareas'.
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    supabase = get_supabase_client()
    
    try:
        query = supabase.table("tareas").select("""
            id, titulo, descripcion, fecha_inicio, fecha_fin, estado, prioridad,
            asignada_a:usuarios_negocios!asignada_a_id(
                id,
                usuario:usuarios(nombre, apellido)
            )
        """).eq("negocio_id", business_id)
        
        # Filtrar por rango de fechas si se especifica
        if fecha_inicio:
            query = query.gte("fecha_inicio", fecha_inicio.isoformat())
        if fecha_fin:
            query = query.lte("fecha_fin", fecha_fin.isoformat())
        
        response = query.execute()
        tareas = response.data or []
        
        # Procesar datos para calendario
        tareas_calendario = []
        for tarea in tareas:
            # Determinar color basado en prioridad y estado
            color = "#6b7280"  # gris por defecto
            if tarea["estado"] == "completada":
                color = "#10b981"  # verde
            elif tarea["estado"] == "en_progreso":
                color = "#3b82f6"  # azul
            elif tarea["prioridad"] == "urgente":
                color = "#ef4444"  # rojo
            elif tarea["prioridad"] == "alta":
                color = "#f59e0b"  # amarillo
            
            asignada_a = None
            if tarea.get("asignada_a") and tarea["asignada_a"].get("usuario"):
                usuario = tarea["asignada_a"]["usuario"]
                asignada_a = {
                    "id": tarea["asignada_a"]["id"],
                    "nombre": f"{usuario['nombre']} {usuario['apellido']}"
                }
            
            tareas_calendario.append(TareaCalendario(
                id=tarea["id"],
                titulo=tarea["titulo"],
                descripcion=tarea["descripcion"],
                fecha_inicio=tarea["fecha_inicio"],
                fecha_fin=tarea["fecha_fin"],
                estado=tarea["estado"],
                prioridad=tarea["prioridad"],
                asignada_a=asignada_a,
                color=color
            ))
        
        return tareas_calendario
        
    except Exception as e:
        print(f"❌ Error al obtener calendario de tareas: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

@router.get("/empleados")
async def get_empleados_negocio(
    business_id: str,
    request: Request,
    _: Any = Depends(PermissionDependency("tareas", "asignar"))
) -> Any:
    """
    Obtener lista de empleados del negocio para asignar tareas.
    Requiere permiso 'puede_asignar_tareas'.
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    supabase = get_supabase_client()
    
    try:
        response = supabase.table("usuarios_negocios").select("""
            id, rol,
            usuario:usuarios!usuarios_negocios_usuario_id_fkey(nombre, apellido, email)
        """).eq("negocio_id", business_id).eq("estado", "aceptado").execute()
        
        empleados = []
        for usuario_negocio in response.data or []:
            if usuario_negocio.get("usuario"):
                usuario = usuario_negocio["usuario"]
                empleados.append({
                    "id": usuario_negocio["id"],
                    "nombre": usuario["nombre"],
                    "apellido": usuario["apellido"],
                    "email": usuario["email"],
                    "rol": usuario_negocio["rol"],
                    "nombre_completo": f"{usuario['nombre']} {usuario['apellido']}"
                })
        
        return {"empleados": empleados}
        
    except Exception as e:
        print(f"❌ Error al obtener empleados: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

@router.get("/estadisticas", response_model=TareaEstadisticas)
async def get_estadisticas_tareas(
    business_id: str,
    request: Request
) -> Any:
    """
    Obtener estadísticas de tareas del negocio.
    Todos los usuarios pueden ver estadísticas, pero filtradas según su rol.
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    supabase = get_supabase_client()
    
    try:
        # Verificar acceso básico al negocio
        business_access = await verify_basic_business_access(business_id, user)
        user_role = business_access.get("rol", "empleado")
        user_negocio_id = business_access.get("id")
        
        # Query base para estadísticas
        base_query = supabase.table("tareas").select("estado, prioridad").eq("negocio_id", business_id)
        
        # Filtrar según el rol del usuario
        if user_role not in ["admin", "propietario"]:
            # Usuario normal: solo ve estadísticas de sus tareas asignadas
            base_query = base_query.eq("asignada_a_id", user_negocio_id)
        
        response = base_query.execute()
        tareas = response.data or []
        
        # Calcular estadísticas
        total_tareas = len(tareas)
        
        # Estadísticas por estado
        pendientes = len([t for t in tareas if t.get("estado") == "pendiente"])
        en_progreso = len([t for t in tareas if t.get("estado") == "en_progreso"])
        completadas = len([t for t in tareas if t.get("estado") == "completada"])
        canceladas = len([t for t in tareas if t.get("estado") == "cancelada"])
        pausadas = len([t for t in tareas if t.get("estado") == "pausada"])
        
        # Estadísticas por prioridad
        baja = len([t for t in tareas if t.get("prioridad") == "baja"])
        media = len([t for t in tareas if t.get("prioridad") == "media"])
        alta = len([t for t in tareas if t.get("prioridad") == "alta"])
        urgente = len([t for t in tareas if t.get("prioridad") == "urgente"])
        
        return TareaEstadisticas(
            total_tareas=total_tareas,
            pendientes=pendientes,
            en_progreso=en_progreso,
            completadas=completadas,
            canceladas=canceladas,
            pausadas=pausadas,
            prioridad_baja=baja,
            prioridad_media=media,
            prioridad_alta=alta,
            prioridad_urgente=urgente
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error al obtener estadísticas de tareas: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

@router.get("/{tarea_id}", response_model=TareaResponse)
async def get_tarea(
    business_id: str,
    tarea_id: str,
    request: Request
) -> Any:
    """
    Obtener una tarea específica.
    Los usuarios pueden ver una tarea si:
    - Son admin/propietario del negocio
    - La tarea está asignada a ellos
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    supabase = get_supabase_client()
    
    try:
        # Verificar acceso básico al negocio
        business_access = await verify_basic_business_access(business_id, user)
        user_role = business_access.get("rol", "empleado")
        user_negocio_id = business_access.get("id")
        
        response = supabase.table("tareas").select("""
            *,
            asignada_a:usuarios_negocios!asignada_a_id(
                id,
                rol,
                usuario:usuarios!usuarios_negocios_usuario_id_fkey(nombre, apellido, email)
            ),
            creada_por:usuarios_negocios!creada_por_id(
                id,
                rol,
                usuario:usuarios!usuarios_negocios_usuario_id_fkey(nombre, apellido, email)
            )
        """).eq("id", tarea_id).eq("negocio_id", business_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")
        
        tarea = response.data[0]
        
        # Verificar permisos de acceso a esta tarea específica
        if user_role not in ["admin", "propietario"]:
            # Usuario normal: solo puede ver tareas asignadas a él
            if tarea.get("asignada_a_id") != user_negocio_id:
                raise HTTPException(
                    status_code=403, 
                    detail="No tienes permisos para ver esta tarea"
                )
        
        # Procesar datos de usuarios
        if tarea.get("asignada_a") and tarea["asignada_a"].get("usuario"):
            usuario = tarea["asignada_a"]["usuario"]
            tarea["asignada_a"] = {
                "id": tarea["asignada_a"]["id"],
                "nombre": usuario["nombre"],
                "apellido": usuario["apellido"],
                "email": usuario["email"]
            }
        
        if tarea.get("creada_por") and tarea["creada_por"].get("usuario"):
            usuario = tarea["creada_por"]["usuario"]
            tarea["creada_por"] = {
                "id": tarea["creada_por"]["id"],
                "nombre": usuario["nombre"],
                "apellido": usuario["apellido"],
                "email": usuario["email"]
            }
        
        return TareaResponse(**tarea)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error al obtener tarea: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

@router.put("/{tarea_id}", response_model=TareaResponse)
async def update_tarea(
    business_id: str,
    tarea_id: str,
    tarea_data: TareaUpdate,
    request: Request,
    _: Any = Depends(PermissionDependency("tareas", "editar"))
) -> Any:
    """
    Actualizar una tarea existente.
    Requiere permiso 'puede_editar_tareas' o ser el creador de la tarea.
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    supabase = get_supabase_client()
    
    try:
        # Verificar que la tarea existe y pertenece al negocio
        tarea_actual = supabase.table("tareas").select("*").eq(
            "id", tarea_id
        ).eq("negocio_id", business_id).execute()
        
        if not tarea_actual.data:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")
        
        # Validar usuario asignado si se está cambiando
        if tarea_data.asignada_a_id:
            assigned_response = supabase.table("usuarios_negocios").select("id").eq(
                "id", tarea_data.asignada_a_id
            ).eq("negocio_id", business_id).eq("estado", "aceptado").execute()
            
            if not assigned_response.data:
                raise HTTPException(
                    status_code=400, 
                    detail="El usuario asignado no pertenece a este negocio"
                )
        
        # Actualizar la tarea
        update_data = {k: v for k, v in tarea_data.model_dump(mode='json').items() if v is not None}
        update_data["actualizado_en"] = datetime.now().isoformat()
        
        response = supabase.table("tareas").update(update_data).eq("id", tarea_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=500, detail="Error al actualizar la tarea")
        
        # Obtener la tarea actualizada con información de usuarios
        tarea_completa = supabase.table("tareas").select("""
            *,
            asignada_a:usuarios_negocios!asignada_a_id(
                id,
                rol,
                usuario:usuarios!usuarios_negocios_usuario_id_fkey(nombre, apellido, email)
            ),
            creada_por:usuarios_negocios!creada_por_id(
                id,
                rol,
                usuario:usuarios!usuarios_negocios_usuario_id_fkey(nombre, apellido, email)
            )
        """).eq("id", tarea_id).execute()
        
        if tarea_completa.data:
            tarea = tarea_completa.data[0]
            
            # Procesar datos de usuarios
            if tarea.get("asignada_a") and tarea["asignada_a"].get("usuario"):
                usuario = tarea["asignada_a"]["usuario"]
                tarea["asignada_a"] = {
                    "id": tarea["asignada_a"]["id"],
                    "nombre": usuario["nombre"],
                    "apellido": usuario["apellido"],
                    "email": usuario["email"]
                }
            
            if tarea.get("creada_por") and tarea["creada_por"].get("usuario"):
                usuario = tarea["creada_por"]["usuario"]
                tarea["creada_por"] = {
                    "id": tarea["creada_por"]["id"],
                    "nombre": usuario["nombre"],
                    "apellido": usuario["apellido"],
                    "email": usuario["email"]
                }
            
            return TareaResponse(**tarea)
        
        return TareaResponse(**response.data[0])
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error al actualizar tarea: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

@router.delete("/{tarea_id}")
async def delete_tarea(
    business_id: str,
    tarea_id: str,
    request: Request,
    _: Any = Depends(PermissionDependency("tareas", "editar"))
) -> Any:
    """
    Eliminar una tarea.
    Requiere permiso 'puede_editar_tareas' o ser el creador de la tarea.
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    supabase = get_supabase_client()
    
    try:
        # Verificar que la tarea existe
        tarea_actual = supabase.table("tareas").select("id").eq(
            "id", tarea_id
        ).eq("negocio_id", business_id).execute()
        
        if not tarea_actual.data:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")
        
        # Eliminar la tarea
        response = supabase.table("tareas").delete().eq("id", tarea_id).execute()
        
        return {"message": "Tarea eliminada correctamente"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error al eliminar tarea: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")
