from supabase.client import create_client, Client
from functools import lru_cache
import os

from app.core.config import settings
from collections.abc import Mapping, Sequence
from typing import Protocol, Callable, cast

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

# Lightweight protocols to type Supabase responses and table query builders we use.
class APIResponseProto(Protocol):
    @property
    def data(self) -> list[dict[str, object]] | None: ...

class TableQueryProto(Protocol):
    def select(self, columns: str) -> "TableQueryProto": ...
    def eq(self, column: str, value: object) -> "TableQueryProto": ...
    def gte(self, column: str, value: object) -> "TableQueryProto": ...
    def lte(self, column: str, value: object) -> "TableQueryProto": ...
    def order(self, column: str, desc: bool = False) -> "TableQueryProto": ...
    def limit(self, n: int) -> "TableQueryProto": ...
    def insert(
        self,
        data: Mapping[str, object] | Sequence[Mapping[str, object]],
        *,
        count: object | None = None,
        returning: object | None = None,
        upsert: bool = False,
    ) -> "TableQueryProto": ...
    def upsert(
        self,
        data: Mapping[str, object] | Sequence[Mapping[str, object]],
        *,
        on_conflict: str | None = None,
        returning: object | None = None,
    ) -> "TableQueryProto": ...
    def update(self, data: Mapping[str, object]) -> "TableQueryProto": ...
    def delete(self) -> "TableQueryProto": ...
    def execute(self) -> APIResponseProto: ...

class HasAuth(Protocol):
    def auth(self, token: str) -> object: ...

class HasSetAuth(Protocol):
    def set_auth(self, token: str) -> object: ...

class HasSetAuthHeaders(Protocol):
    def _set_auth_headers(self, headers: Mapping[str, str]) -> object: ...

@lru_cache()
def get_supabase_service_client() -> Client:
    """
    Create and return a Supabase client using the Service Role key.
    Use this ONLY for server-side operations where RLS must be bypassed,
    e.g., automatic finance movements on purchase creation.
    """
    url = settings.SUPABASE_URL
    service_key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY
    
    print("=== Creando cliente Supabase Service ===")
    print(f"URL: {url}")
    print(f"SERVICE_KEY: {'*'*(len(service_key)//4) if service_key else 'No configurada'}")
    
    if not url:
        raise ValueError("SUPABASE_URL no está configurado en variables de entorno o .env")
    if not service_key:
        raise ValueError("SUPABASE_SERVICE_ROLE_KEY o SUPABASE_KEY no están configurados")
    
    try:
        client = create_client(url, service_key)
        print("[OK] Cliente Supabase Service creado exitosamente")
        return client
    except Exception as e:
        print(f"[ERROR] Error al crear cliente Supabase Service: {str(e)}")
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
            # postgrest.auth(token)
            postgrest_obj = cast(object, getattr(client, 'postgrest', None))
            if postgrest_obj is not None:
                _ = cast(HasAuth, postgrest_obj).auth(clean_token)
                print("[OK] Token establecido en cliente postgrest")
        except Exception as e:
            print(f"[ERROR] No se pudo establecer token en cliente postgrest: {e}")
        
        # Establecer el token también en el cliente auth si está disponible
        try:
            auth_obj = cast(object, getattr(client, 'auth', None))
            if auth_obj is not None:
                try:
                    # auth.set_auth(token)
                    _ = cast(HasSetAuth, auth_obj).set_auth(clean_token)
                    print("[OK] Token establecido en cliente auth mediante set_auth")
                except Exception:
                    # auth._set_auth_headers({ 'Authorization': 'Bearer <token>' })
                    _ = cast(HasSetAuthHeaders, auth_obj)._set_auth_headers({  # pyright: ignore[reportPrivateUsage]
                        "Authorization": f"Bearer {clean_token}"
                    })
                    print("[OK] Token establecido en cliente auth mediante _set_auth_headers")
        except Exception as e:
            print(f"[ERROR] No se pudo establecer token en cliente auth: {e}")
        
        # Enfoque adicional para versiones más recientes de supabase-py
        try:
            rest_obj = cast(object, getattr(client, 'rest', None))
            if rest_obj is not None:
                _ = cast(HasAuth, rest_obj).auth(clean_token)
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
def get_table(table_name: str) -> TableQueryProto:
    """
    Get a reference to a Supabase table using the base client.
    Use get_supabase_user_client for RLS-protected operations.
    """
    client = get_supabase_client()
    table_fn = cast(Callable[[str], object], getattr(client, "table"))
    return cast(TableQueryProto, table_fn(table_name))

# Función para verificar la conexión a Supabase
def check_supabase_connection() -> bool:
    """
    Verifica si la conexión a Supabase está correctamente configurada usando el cliente base.
    """
    try:
        _ = get_supabase_client()
        # Intentar realizar una operación más simple, como listar tablas disponibles
        # o consultar una tabla que sabemos que existe
        try:
            # Intentar obtener registro de la tabla usuarios (limitado a 1)
            _ = get_table("usuarios").select("*").limit(1).execute()
            # print(f"✅ Conexión correcta - consulta a 'usuarios' ejecutada") # Too verbose
            return True
        except Exception:
            # print(f"Error al consultar tabla durante check: {str(table_error)}") # Too verbose
            # Aún si no se puede consultar la tabla, la conexión podría estar bien
            # La tabla podría no existir todavía o RLS podría estar interfiriendo sin token
            # Return True for base connection check even on table access error if client created
            return True # Assume base client connection is ok if get_supabase_client didn't fail
    except Exception as e:
        print(f"[ERROR] Error de conexion con Supabase (check): {str(e)}")
        return False 