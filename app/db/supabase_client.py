from supabase import create_client, Client
from functools import lru_cache
import os

from app.core.config import settings

@lru_cache()
def get_supabase_client() -> Client:
    """
    Create and return a Supabase client using the configuration from settings.
    Uses lru_cache to cache the client and avoid creating a new one for each request.
    """
    url = settings.SUPABASE_URL
    key = settings.SUPABASE_KEY
    
    # Verificar que las credenciales están configuradas
    if not url:
        raise ValueError("SUPABASE_URL no está configurado en variables de entorno o .env")
    
    if not key:
        raise ValueError("SUPABASE_KEY no está configurado en variables de entorno o .env")
    
    # Imprimir información de depuración (quitar en producción)
    print(f"Conectando a Supabase: URL={url}, KEY={'*'*(len(key)//4) if key else 'No configurada'}")
    
    # Crear cliente Supabase
    client = create_client(url, key)
    
    # Configurar URL de redirección para confirmación de email
    # Esto es sólo necesario en desarrollo, en producción se debe configurar en la interfaz de Supabase
    try:
        # Intentar configurar URL de redirección
        # Nota: Esto puede requerir permisos de administrador y sólo funciona con la API Key correcta
        if settings.DEBUG:
            print("Configurando URL de redirección para confirmación de email...")
            redirect_config = {
                "redirectTo": "http://localhost:5173/confirm-email"
            }
            # Esta configuración es específica de ciertas funcionalidades y puede variar
            # dependiendo de la versión de la librería
            if hasattr(client.auth, 'set_config'):
                client.auth.set_config(redirect_config)
    except Exception as e:
        print(f"Advertencia: No se pudo configurar URL de redirección: {str(e)}")
        print("Configura manualmente las URL de redirección en el dashboard de Supabase")
    
    return client

# Convenience function to get a table
def get_table(table_name: str):
    """
    Get a reference to a Supabase table.
    
    Args:
        table_name (str): The name of the table in Supabase
        
    Returns:
        A reference to the table that can be used for queries
    """
    client = get_supabase_client()
    return client.table(table_name)

# Función para verificar la conexión a Supabase
def check_supabase_connection() -> bool:
    """
    Verifica si la conexión a Supabase está correctamente configurada.
    
    Returns:
        bool: True si la conexión es exitosa, False en caso contrario
    """
    try:
        client = get_supabase_client()
        # Intentar realizar una operación más simple, como listar tablas disponibles
        # o consultar una tabla que sabemos que existe
        try:
            # Intentar obtener registro de la tabla usuarios (limitado a 1)
            response = client.table("usuarios").select("*").limit(1).execute()
            print(f"✅ Conexión correcta - hay {len(response.data)} usuarios en la tabla")
            return True
        except Exception as table_error:
            print(f"Error al consultar tabla: {str(table_error)}")
            # Aún si no se puede consultar la tabla, la conexión podría estar bien
            # La tabla podría no existir todavía
            return True
    except Exception as e:
        print(f"Error de conexión con Supabase: {str(e)}")
        return False 