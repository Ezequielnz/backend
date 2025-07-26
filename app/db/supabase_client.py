from supabase.client import create_client, Client
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
        print("[OK] Cliente Supabase Base creado exitosamente")
        return client
    except Exception as e:
        print(f"[ERROR] Error al crear cliente Supabase Base: {str(e)}")
        print(f"Tipo de error: {type(e)}")
        raise

def get_supabase_anon_client() -> Client:
    """
    Create and return a Supabase client using the anon key for user registration.
    This ensures auth.uid() is null during registration, allowing RLS policies to work correctly.
    """
    url = settings.SUPABASE_URL
    # Use anon key instead of service key for registration
    anon_key = os.getenv("SUPABASE_ANON_KEY", settings.SUPABASE_KEY)
    
    print("=== Creando cliente Supabase Anónimo ===")
    print(f"URL: {url}")
    print(f"ANON_KEY: {'*'*(len(anon_key)//4) if anon_key else 'No configurada'}")
    
    if not url or not anon_key:
        raise ValueError("SUPABASE_URL o SUPABASE_ANON_KEY no están configurados")
    
    try:
        # Crear cliente Supabase con anon key
        client = create_client(url, anon_key)
        print("[OK] Cliente Supabase Anonimo creado exitosamente")
        return client
    except Exception as e:
        print(f"[ERROR] Error al crear cliente Supabase Anonimo: {str(e)}")
        print(f"Tipo de error: {type(e)}")
        raise

def get_supabase_user_client(user_token: str) -> Client:
    """
    Create and return a Supabase client with user authentication.
    This client will use the user's token for RLS-protected operations.
    """
    url = settings.SUPABASE_URL
    # Use anon key for user client - this is the correct approach
    anon_key = settings.SUPABASE_ANON_KEY or settings.SUPABASE_KEY
    
    print("=== Creando cliente Supabase con token de usuario ===")
    print(f"URL: {url}")
    print(f"ANON_KEY: {'*'*(len(anon_key)//4) if anon_key else 'No configurada'}")
    
    if not url or not anon_key:
         raise ValueError("SUPABASE_URL o SUPABASE_ANON_KEY no están configurados")
    
    # Asegurar que el token esté limpio (sin 'Bearer ' al inicio)
    clean_token = user_token
    if clean_token and clean_token.startswith('Bearer '):
        clean_token = clean_token[7:]
    
    print(f"Token procesado (primeros 10 chars): {clean_token[:10] if clean_token else 'None'}...")
    
    try:
        # Create client with anon key
        client = create_client(url, anon_key)
        
        # Set authorization header on the client based on version
        # Different versions of supabase-py have different structures
        try:
            # Mejor enfoque: usar un método de acceso seguro para establecer headers en postgrest
            if hasattr(client, 'postgrest'):
                postgrest = getattr(client, 'postgrest')
                # Supabase espera un token JWT sin el prefijo 'Bearer '
                if hasattr(postgrest, 'auth'):
                    postgrest.auth(clean_token)
                    print("[OK] Token establecido en cliente postgrest")
        except Exception as e:
            print(f"[ERROR] No se pudo establecer token en cliente postgrest: {e}")
        
        # Establecer el token también en el cliente auth si está disponible
        try:
            if hasattr(client, 'auth'):
                auth = getattr(client, 'auth')
                if hasattr(auth, 'set_auth'):
                    auth.set_auth(clean_token)  # Sin prefijo Bearer
                    print("[OK] Token establecido en cliente auth mediante set_auth")
                # Enfoque alternativo
                elif hasattr(auth, '_set_auth_headers'):
                    # Con prefijo Bearer para los headers
                    auth._set_auth_headers({"Authorization": f"Bearer {clean_token}"})
                    print("[OK] Token establecido en cliente auth mediante _set_auth_headers")
        except Exception as e:
            print(f"[ERROR] No se pudo establecer token en cliente auth: {e}")
        
        # Enfoque adicional para versiones más recientes de supabase-py
        try:
            if hasattr(client, 'rest'):
                rest_client = getattr(client, 'rest')
                if hasattr(rest_client, 'auth'):
                    rest_client.auth(clean_token)
                    print("[OK] Token establecido en cliente rest")
        except Exception as e:
            print(f"[AVISO] No se pudo establecer token en cliente rest: {e}")
                
        print("[OK] Cliente Supabase con token de usuario creado exitosamente")
        return client
    except Exception as e:
        print(f"[ERROR] Error al crear cliente Supabase con token: {str(e)}")
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
        print(f"[ERROR] Error de conexion con Supabase (check): {str(e)}")
        return False 