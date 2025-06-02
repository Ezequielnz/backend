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
        
        # Verificar si hay registros huérfanos para este usuario
        print(f"Checking for orphaned user-business relationships for user {user.id}")
        orphaned_check = supabase.table("usuarios_negocios") \
            .select("id, negocio_id") \
            .eq("usuario_id", user.id) \
            .execute()
        
        if orphaned_check.data:
            print(f"Found {len(orphaned_check.data)} existing relationships for user {user.id}")
            for relationship in orphaned_check.data:
                # Verificar si el negocio asociado existe
                business_check = supabase.table("negocios") \
                    .select("id") \
                    .eq("id", relationship["negocio_id"]) \
                    .execute()
                
                if not business_check.data:
                    # El negocio no existe, eliminar la relación huérfana
                    print(f"Removing orphaned relationship {relationship['id']} for non-existent business {relationship['negocio_id']}")
                    supabase.table("usuarios_negocios") \
                        .delete() \
                        .eq("id", relationship["id"]) \
                        .execute()
                else:
                    print(f"Valid relationship found: user {user.id} -> business {relationship['negocio_id']}")
        else:
            print(f"No existing relationships found for user {user.id}")
        
        try:
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
                # Rollback: eliminar el negocio creado
                print(f"Rolling back business creation for business_id: {business_id}")
                supabase.table("negocios").delete().eq("id", business_id).execute()
                
                # Verificar si es un error de constraint único
                if "23505" in str(user_business_link_response.error):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Ya existe una relación para este usuario. Puede que tengas un negocio pendiente de configuración."
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Error linking user to business: {user_business_link_response.error.message}"
                    )

            if not user_business_link_response.data or len(user_business_link_response.data) == 0:
                print("❌ Supabase INSERT usuarios_negocios returned no data")
                # Rollback: eliminar el negocio creado
                print(f"Rolling back business creation for business_id: {business_id}")
                supabase.table("negocios").delete().eq("id", business_id).execute()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error linking user to business - no data returned."
                )
                
        except HTTPException:
            raise  # Re-raise HTTPExceptions
        except Exception as e:
            print(f"❌ Unexpected error linking user to business: {e}")
            # Rollback: eliminar el negocio creado
            print(f"Rolling back business creation for business_id: {business_id}")
            supabase.table("negocios").delete().eq("id", business_id).execute()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error linking user to business: {str(e)}"
            )

        usuario_negocio_id = user_business_link_response.data[0].get("id")
        print(f"✅ User {user.id} linked to business {business_id} with usuario_negocio_id: {usuario_negocio_id}")

        # 3. Optionally, set initial admin permissions in 'permisos_usuario_negocio'
        # Make this non-critical - if it fails, the business creation should still succeed
        try:
            initial_permissions = {
                "usuario_negocio_id": usuario_negocio_id,
                "acceso_total": True,
                "puede_ver_tareas": True,
                "puede_asignar_tareas": True,
                "puede_editar_tareas": True,
                "recurso": "general",
                "accion": "manage",
            }
            print(f"Setting initial permissions for usuario_negocio_id: {usuario_negocio_id}")
            
            permissions_response = supabase.table("permisos_usuario_negocio").insert([initial_permissions]).execute()
            
            if hasattr(permissions_response, 'error') and permissions_response.error:
                print(f"⚠️ Warning: Could not set initial permissions: {permissions_response.error}")
            elif permissions_response.data:
                print(f"✅ Initial permissions set successfully")
            else:
                print("⚠️ Warning: Could not set initial permissions - No data returned")
                
        except Exception as permissions_error:
            print(f"⚠️ Warning: Error setting initial permissions (non-critical): {permissions_error}")
            # Continue with business creation even if permissions fail

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
        print(f"🔍 Getting businesses for user: {user.id}")
        
        # Get all businesses linked to the user through usuarios_negocios
        # Select specific fields to match the Business model
        response = supabase.table("usuarios_negocios") \
            .select("rol, negocios(id, nombre, creada_por, creada_en)") \
            .eq("usuario_id", user.id) \
            .execute()

        print(f"🔍 Raw response from usuarios_negocios: {response.data}")

        if not response.data:
            print("🔍 No business relationships found for user")
            return []

        # Transform the response to match the Business model
        businesses = []
        for item in response.data:
            print(f"🔍 Processing item: {item}")
            negocio_data = item.get("negocios")
            if negocio_data:
                print(f"🔍 Found business data: {negocio_data}")
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
                print(f"🔍 Added business to list: {business_obj}")
            else:
                print(f"🔍 No business data found for item: {item}")

        print(f"🔍 Final businesses list: {businesses}")
        print(f"🔍 Total businesses found: {len(businesses)}")
        return businesses

    except Exception as e:
        print(f"Error getting businesses: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting businesses: {str(e)}",
        )

@router.get("/{business_id}", response_model=Business)
async def get_business_by_id(business_id: str, request: Request) -> Any:
    """Get a specific business by ID for the current user."""
    user = request.state.user
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated.",
        )

    supabase = get_supabase_client()

    try:
        # Verify that the user has access to this business through usuarios_negocios
        # and get the business data in one query
        # Solo seleccionar los campos que realmente existen en la tabla negocios
        response = supabase.table("usuarios_negocios") \
            .select("rol, negocios(id, nombre, creada_por, creada_en)") \
            .eq("usuario_id", user.id) \
            .eq("negocio_id", business_id) \
            .execute()

        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found or you don't have access to it.",
            )

        # Extract business data from the response
        user_business_data = response.data[0]
        negocio_data = user_business_data.get("negocios")
        
        if not negocio_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business data not found.",
            )

        # Construct the Business object with only the fields that exist
        business_obj = {
            "id": negocio_data.get("id"),
            "nombre": negocio_data.get("nombre"),
            "creada_por": negocio_data.get("creada_por"),
            "creada_en": negocio_data.get("creada_en"),
            "rol": user_business_data.get("rol"),
        }

        return business_obj

    except HTTPException:
        raise  # Re-raise HTTPExceptions
    except Exception as e:
        print(f"Error getting business by ID: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting business: {str(e)}",
        )

@router.delete("/{business_id}")
async def delete_business(business_id: str, request: Request) -> Any:
    """Delete a business and all its related data."""
    user = request.state.user
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated.",
        )

    supabase = get_supabase_client()

    try:
        # First, verify that the user has admin access to this business
        response = supabase.table("usuarios_negocios") \
            .select("rol") \
            .eq("usuario_id", user.id) \
            .eq("negocio_id", business_id) \
            .execute()

        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found or you don't have access to it.",
            )

        user_role = response.data[0].get("rol")
        if user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can delete businesses.",
            )

        # Delete in the correct order to respect foreign key constraints
        # 1. First, get all usuario_negocio_ids for this business
        print(f"Getting usuario_negocio relationships for business {business_id}")
        user_business_ids_response = supabase.table("usuarios_negocios") \
            .select("id") \
            .eq("negocio_id", business_id) \
            .execute()
        
        if user_business_ids_response.data:
            # Extract just the IDs
            usuario_negocio_ids = [item["id"] for item in user_business_ids_response.data]
            print(f"Found usuario_negocio_ids: {usuario_negocio_ids}")
            
            # Delete permissions for these usuario_negocio relationships
            if usuario_negocio_ids:
                print(f"Deleting permissions for usuario_negocio_ids: {usuario_negocio_ids}")
                permissions_response = supabase.table("permisos_usuario_negocio") \
                    .delete() \
                    .in_("usuario_negocio_id", usuario_negocio_ids) \
                    .execute()
                print(f"Permissions deletion response: {permissions_response}")

        # 2. Delete user-business relationships
        print(f"Deleting user-business relationships for business {business_id}")
        user_business_response = supabase.table("usuarios_negocios") \
            .delete() \
            .eq("negocio_id", business_id) \
            .execute()

        # 3. Delete products (if any)
        print(f"Deleting products for business {business_id}")
        products_response = supabase.table("productos") \
            .delete() \
            .eq("negocio_id", business_id) \
            .execute()

        # 4. Delete categories (if any)
        print(f"Deleting categories for business {business_id}")
        categories_response = supabase.table("categorias") \
            .delete() \
            .eq("negocio_id", business_id) \
            .execute()

        # 5. Finally, delete the business itself
        print(f"Deleting business {business_id}")
        business_response = supabase.table("negocios") \
            .delete() \
            .eq("id", business_id) \
            .execute()

        if hasattr(business_response, 'error') and business_response.error:
            print(f"❌ Supabase DELETE error: {business_response.error}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error deleting business: {business_response.error.message}"
            )

        print(f"✅ Business {business_id} deleted successfully")
        return {"message": "Business deleted successfully", "business_id": business_id}

    except HTTPException:
        raise  # Re-raise HTTPExceptions
    except Exception as e:
        print(f"❌ Error deleting business: {type(e).__name__} - {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting business: {str(e)}",
        )

@router.get("/debug/{user_id}")
async def debug_user_businesses(user_id: str, request: Request) -> Any:
    """Debug endpoint to see all data for a user."""
    supabase = get_supabase_client()
    
    try:
        print(f"🐛 DEBUG: Checking data for user {user_id}")
        
        # 1. Check usuarios_negocios table
        user_business_response = supabase.table("usuarios_negocios") \
            .select("*") \
            .eq("usuario_id", user_id) \
            .execute()
        
        print(f"🐛 usuarios_negocios records: {user_business_response.data}")
        
        # 2. Check negocios table
        all_businesses_response = supabase.table("negocios") \
            .select("*") \
            .eq("creada_por", user_id) \
            .execute()
        
        print(f"🐛 negocios records: {all_businesses_response.data}")
        
        # 3. Check for orphaned records
        if user_business_response.data:
            business_ids = [item["negocio_id"] for item in user_business_response.data]
            print(f"🐛 Business IDs from relationships: {business_ids}")
            
            for business_id in business_ids:
                business_check = supabase.table("negocios") \
                    .select("*") \
                    .eq("id", business_id) \
                    .execute()
                print(f"🐛 Business {business_id} exists: {bool(business_check.data)}")
                if business_check.data:
                    print(f"🐛 Business {business_id} data: {business_check.data[0]}")
        
        return {
            "user_id": user_id,
            "user_business_relationships": user_business_response.data,
            "businesses_created_by_user": all_businesses_response.data,
            "total_relationships": len(user_business_response.data or []),
            "total_businesses": len(all_businesses_response.data or [])
        }
        
    except Exception as e:
        print(f"🐛 DEBUG ERROR: {e}")
        return {"error": str(e)}

@router.post("/repair/{user_id}")
async def repair_user_businesses(user_id: str, request: Request) -> Any:
    """Repair missing user-business relationships for orphaned businesses."""
    supabase = get_supabase_client()
    
    try:
        print(f"🔧 REPAIR: Starting repair for user {user_id}")
        
        # 1. Get all businesses created by this user
        all_businesses_response = supabase.table("negocios") \
            .select("*") \
            .eq("creada_por", user_id) \
            .execute()
        
        if not all_businesses_response.data:
            return {"message": "No businesses found for user", "repaired": 0}
        
        # 2. Get existing relationships
        existing_relationships_response = supabase.table("usuarios_negocios") \
            .select("negocio_id") \
            .eq("usuario_id", user_id) \
            .execute()
        
        existing_business_ids = [item["negocio_id"] for item in existing_relationships_response.data or []]
        print(f"🔧 Existing relationships for businesses: {existing_business_ids}")
        
        # 3. Find orphaned businesses (businesses without relationships)
        orphaned_businesses = []
        for business in all_businesses_response.data:
            if business["id"] not in existing_business_ids:
                orphaned_businesses.append(business)
        
        print(f"🔧 Found {len(orphaned_businesses)} orphaned businesses")
        
        # 4. Create missing relationships
        repaired_count = 0
        for business in orphaned_businesses:
            print(f"🔧 Creating relationship for business {business['id']} ({business['nombre']})")
            
            try:
                relationship_response = supabase.table("usuarios_negocios").insert({
                    "usuario_id": user_id,
                    "negocio_id": business["id"],
                    "rol": "admin",
                    "estado": "aceptado",
                    "invitado_por": None
                }).execute()
                
                if relationship_response.data:
                    print(f"✅ Created relationship for business {business['id']}")
                    repaired_count += 1
                else:
                    print(f"❌ Failed to create relationship for business {business['id']}")
                    
            except Exception as e:
                print(f"❌ Error creating relationship for business {business['id']}: {e}")
        
        return {
            "message": f"Repair completed. {repaired_count} relationships created.",
            "user_id": user_id,
            "total_businesses": len(all_businesses_response.data),
            "orphaned_businesses_found": len(orphaned_businesses),
            "relationships_repaired": repaired_count
        }
        
    except Exception as e:
        print(f"🔧 REPAIR ERROR: {e}")
        return {"error": str(e)} 