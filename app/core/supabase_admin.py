"""
Módulo para operaciones administrativas de Supabase
Incluye funciones que requieren permisos de administrador
"""
import os
import httpx
from typing import Optional
from app.core.config import settings

class SupabaseAdmin:
    def __init__(self):
        self.project_url = settings.SUPABASE_URL
        # Usar service role key si está disponible, sino usar la key normal
        self.service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY
        self.headers = {
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
            "apikey": self.service_role_key
        }
    
    async def delete_auth_user(self, user_id: str) -> bool:
        """
        Eliminar usuario de auth.users usando la API de administración
        """
        try:
            print(f"🗑️ Eliminando usuario {user_id} de auth.users...")
            
            async with httpx.AsyncClient() as client:
                # URL para eliminar usuario usando la API de administración
                url = f"{self.project_url}/auth/v1/admin/users/{user_id}"
                
                response = await client.delete(url, headers=self.headers)
                
                if response.status_code == 200:
                    print(f"✅ Usuario {user_id} eliminado de auth.users")
                    return True
                elif response.status_code == 404:
                    print(f"⚠️ Usuario {user_id} no encontrado en auth.users (ya eliminado)")
                    return True
                else:
                    print(f"❌ Error eliminando usuario de auth.users: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            print(f"❌ Excepción eliminando usuario de auth.users: {e}")
            return False
    
    async def get_auth_user(self, user_id: str) -> Optional[dict]:
        """
        Obtener información de usuario de auth.users
        """
        try:
            async with httpx.AsyncClient() as client:
                url = f"{self.project_url}/auth/v1/admin/users/{user_id}"
                
                response = await client.get(url, headers=self.headers)
                
                if response.status_code == 200:
                    return response.json()
                else:
                    return None
                    
        except Exception as e:
            print(f"❌ Error obteniendo usuario de auth.users: {e}")
            return None

# Instancia global
supabase_admin = SupabaseAdmin() 