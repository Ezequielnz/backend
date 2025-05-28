from supabase import create_client, Client
from functools import lru_cache
import os

from app.core.config import settings

@lru_cache()
def get_supabase_client() -> Client:
    """
    Create and return a Supabase client using the configuration from settings.
    Uses lru_cache to cache the client and avoid creating a new one for each request.
    This client is typically used for operations that don't require user authentication (e.g., public reads, auth operations themselves).
    """
    url = settings.SUPABASE_URL
    key = settings.SUPABASE_KEY
    
    print("=== Creando cliente Supabase Base ===")
    print(f"URL: {url}")
    print(f"KEY: {'*'*(len(key)//4) if key else 'No configurada'}")
    
    # Verificar que las credenciales están configuradas
    if not url:
        raise ValueError("SUPABASE_URL no está configurado en variables de entorno o .env")
    
    if not key:
        raise ValueError("SUPABASE_KEY no está configurado en variables de entorno o .env")
    
    try:
        # Crear cliente Supabase
        client = create_client(url, key)
        print("✅ Cliente Supabase Base creado exitosamente")
        return client
    except Exception as e:
        print(f"❌ Error al crear cliente Supabase Base: {str(e)}")
        print(f"Tipo de error: {type(e)}")
        raise

def get_supabase_user_client(user_token: str) -> Client:
    """
    Create and return a Supabase client authenticated with the user's token.
    This client should be used for operations protected by RLS.
    """
    url = settings.SUPABASE_URL
    key = settings.SUPABASE_KEY # Although user token is used for auth, anon key might still be needed for some features
    
    print("=== Creando cliente Supabase con token de usuario ===")
    print(f"URL: {url}")
    print(f"KEY: {'*'*(len(key)//4) if key else 'No configurada'}")
    print(f"Token de usuario (primeros 10 chars): {user_token[:10]}...")
    
    if not url or not key:
         raise ValueError("SUPABASE_URL o SUPABASE_KEY no están configurados")
    
    try:
        # Crear cliente Supabase y establecer el token de la sesión
        client = create_client(url, key)
        print("Intentando establecer sesión con token...")
        client.auth.set_session(access_token=user_token, refresh_token=None) # We only need access token for RLS
        print("✅ Sesión establecida en cliente Supabase con token")
        # Opcional: Verificar si el cliente está autenticado (puede no ser necesario/posible fácilmente)
        # try:
        #     user_check = client.auth.get_user()
        #     print(f"Verificación de usuario en cliente con token: {user_check.user.id if user_check and user_check.user else 'None'}")
        # except Exception as check_e:
        #      print(f"Error durante verificación de usuario en cliente con token: {check_e}")
             
        print("✅ Cliente Supabase con token creado exitosamente")
        return client
    except Exception as e:
        print(f"❌ Error al crear cliente Supabase con token o establecer sesión: {str(e)}")
        print(f"Tipo de error: {type(e)}")
        raise

# Convenience function to get a table (consider if this should use user client or base client)
# Current implementation uses the base client - modify if RLS applies to basic table access
def get_table(table_name: str):
    """
    Get a reference to a Supabase table using the base client.
    Use get_supabase_user_client for RLS-protected operations.
    """
    client = get_supabase_client()
    return client.table(table_name)

# Función para verificar la conexión a Supabase
def check_supabase_connection() -> bool:
    """
    Verifica si la conexión a Supabase está correctamente configurada usando el cliente base.
    """
    try:
        client = get_supabase_client()
        # Intentar realizar una operación más simple, como listar tablas disponibles
        # o consultar una tabla que sabemos que existe
        try:
            # Intentar obtener registro de la tabla usuarios (limitado a 1)
            response = client.table("usuarios").select("*").limit(1).execute()
            # print(f"✅ Conexión correcta - hay {len(response.data)} usuarios en la tabla") # Too verbose
            return True
        except Exception as table_error:
            # print(f"Error al consultar tabla durante check: {str(table_error)}") # Too verbose
            # Aún si no se puede consultar la tabla, la conexión podría estar bien
            # La tabla podría no existir todavía o RLS podría estar interfiriendo sin token
            # Return True for base connection check even on table access error if client created
            return True # Assume base client connection is ok if get_supabase_client didn't fail
    except Exception as e:
        print(f"❌ Error de conexión con Supabase (check): {str(e)}")
        return False 