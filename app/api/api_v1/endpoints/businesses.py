from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from app.types.auth import User
from app.api.deps import get_current_user
from app.db.supabase_client import get_supabase_client # Revertir a cliente base
from app.schemas.business import BusinessCreate, Business
from supabase.lib.client_options import ClientOptions

router = APIRouter()

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_business(business_data: BusinessCreate, request: Request) -> Any:
    """Create a new business and assign the creating user as admin."""
    user = request.state.user
    # Asegurarse de que el usuario está autenticado (validado por middleware)
    if not user or not hasattr(user, 'id'): # Verificar que el objeto user tiene id
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated or user ID not available.",
        )

    # Usar el cliente Supabase base - la autenticación para RLS debe venir del token en la cabecera
    supabase = get_supabase_client()

    try:
        # 1. Create the new business in the 'negocios' table
        print(f"Attempting to create business: {business_data.nombre} for user {user.id}")
        # Incluir explícitamente el usuario_id como creada_por
        # Con RLS ENABLE INSERT WITH CHECK (true) + autenticación por token, esto debería pasar
        insert_data = {
            "nombre": business_data.nombre,
            "creada_por": str(user.id) # Asegurar que es string, Supabase espera UUID string
        }
        print(f"Insert data: {insert_data}")

        business_response = supabase.table("negocios").insert([insert_data]).execute()

        # === Manejo explícito de errores de Supabase ===
        if hasattr(business_response, 'error') and business_response.error:
             print(f"❌ Supabase INSERT error: {business_response.error}")
             raise HTTPException(
                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, # O 400 dependiendo del error
                 detail=f"Supabase error creating business: {business_response.error.message}"
             )

        if not business_response.data or len(business_response.data) == 0:
             print("❌ Supabase INSERT returned no data")
             raise HTTPException(
                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail="Supabase did not return created business data."
             )
        # =============================================

        new_business = business_response.data[0]
        business_id = new_business.get("id")
        print(f"✅ Business created with ID: {business_id}")

        # 2. Link the creating user to the business in 'usuarios_negocios' as admin
        print(f"Linking user {user.id} to business {business_id} as admin.")
        # Usar el cliente base - la RLS para esta tabla también necesita permitir la inserción para el usuario autenticado
        # Si esta tabla también tiene RLS, su política INSERT debe ser revisada.
        user_business_link_response = supabase.table("usuarios_negocios").insert({
            "usuario_id": str(user.id), # Asegurar que es string
            "negocio_id": business_id,
            "rol": "admin", # Assign admin role to the creator
            "estado": "aceptado", # Creator is automatically accepted
            "invitado_por": None # Explicitamente establecer a NULL si no hay un invitador
        }).execute()
        
        # === Manejo explícito de errores de Supabase ===
        if hasattr(user_business_link_response, 'error') and user_business_link_response.error:
             print(f"❌ Supabase INSERT usuarios_negocios error: {user_business_link_response.error}")
             # Considerar rollback de la creación del negocio si esta falla
             # Opcional: supabase.table("negocios").delete().eq("id", business_id).execute()
             raise HTTPException(
                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Supabase error linking user to business: {user_business_link_response.error.message}"
             )
        # =============================================

        if not user_business_link_response.data or len(user_business_link_response.data) == 0:
             print("❌ Supabase INSERT usuarios_negocios returned no data")
             raise Exception("Error linking user to business.")
             
        usuario_negocio_id = user_business_link_response.data[0].get("id")
        print(f"✅ User {user.id} linked to business {business_id} with usuario_negocio_id: {usuario_negocio_id}")

        # 3. Optionally, set initial admin permissions in 'permisos_usuario_negocio'
        # You can define default permissions for admins here
        initial_permissions = {
            "usuario_negocio_id": usuario_negocio_id,
            "acceso_total": True, # Admins might have total access by default
            # Set specific permissions as True for admin, e.g.,
            "puede_ver_tareas": True,
            "puede_asignar_tareas": True,
            "puede_editar_tareas": True,
            "recurso": "general", # Añadir valor para la columna recurso (ajusta según tu lógica)
            "accion": "manage", # Añadir valor para la columna accion (ajusta según tu lógica)
            # Las columnas 'puede_ver_productos', 'puede_editar_productos', 'puede_ver_categorias', 'puede_editar_categorias' no existen en la tabla
            # "puede_ver_productos": True,
            # "puede_editar_productos": True,
            # "puede_ver_categorias": True,
            # "puede_editar_categorias": True,
            # Add other admin permissions here
        }
        print(f"Setting initial permissions for usuario_negocio_id: {usuario_negocio_id}")
        # Usar el cliente base
        permissions_response = supabase.table("permisos_usuario_negocio").insert([initial_permissions]).execute()
        
        # === Manejo explícito de errores de Supabase ===
        if hasattr(permissions_response, 'error') and permissions_response.error:
             print(f"❌ Supabase INSERT permisos_usuario_negocio error: {permissions_response.error}")
             # Esto podría no ser un error crítico dependiendo de tu lógica
             # Si es crítico, considera rollback de pasos anteriores
             print("Warning: Could not set initial permissions.") # Log warning
        # =============================================

        if not permissions_response.data:
            print("Warning: Could not set initial permissions - No data returned.") # Log warning

        return {"message": "Business created successfully", "business_id": business_id}

    except HTTPException:
        raise # Re-lanzar HTTPExceptions que ya creamos
    except Exception as e:
        print(f"❌ Error general creating business: {type(e).__name__} - {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating business: {str(e)}",
        )

@router.get("/", response_model=List[Business])
async def get_businesses(request: Request) -> Any:
    """Get all businesses for the current user."""
    user = request.state.user
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated.",
        )

    supabase = get_supabase_client()

    try:
        # Get all businesses linked to the user through usuarios_negocios
        # Select specific fields to match the Business model
        response = supabase.table("usuarios_negocios") \
            .select("rol, negocios(id, nombre, creada_por, creada_en)") \
            .eq("usuario_id", user.id) \
            .execute()

        if not response.data:
            return []

        # Transform the response to match the Business model
        businesses = []
        for item in response.data:
            negocio_data = item.get("negocios")
            if negocio_data:
                # Construir el objeto Business a partir de los datos de la respuesta
                business_obj = {
                    "id": negocio_data.get("id"),
                    "nombre": negocio_data.get("nombre"),
                    "creada_por": negocio_data.get("creada_por"),
                    "creada_en": negocio_data.get("creada_en"),
                    "rol": item.get("rol"),
                    # Incluir campos opcionales si existen en la tabla y el modelo
                    "descripcion": negocio_data.get("descripcion"),
                    "direccion": negocio_data.get("direccion"),
                    "telefono": negocio_data.get("telefono"),
                    "email": negocio_data.get("email"),
                    "logo_url": negocio_data.get("logo_url"),
                    # No incluir updated_at ya que no está en la tabla negocios
                }
                businesses.append(business_obj)

        return businesses

    except Exception as e:
        print(f"Error getting businesses: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting businesses: {str(e)}",
        ) 