import sys
import asyncio

sys.path.append('c:\\Users\\Usuario\\Documents\\Workspace\\micro_pymes\\backend')
from app.db.supabase_client import get_supabase_service_client

async def main():
    db = get_supabase_service_client()
    user_id = '3fce0a99-76c4-4959-9b70-e7cbfc9c4143'
    
    # Get user profile
    user_res = db.table("usuarios").select("*").eq("id", user_id).execute()
    print("USER PROFILE:")
    print(user_res.data)
    
    # Get businesses where this user is owner or has role
    # Wait, what are the tables? Let's check businesses/memberships.
    # Let's list tables first or run a generic select.
    # Let's see what tables exist. We can query 'negocios' or 'negocio_usuarios'.
    try:
        negocios = db.table("negocios").select("*").execute()
        print("\nALL BUSINESSES:")
        print(negocios.data)
    except Exception as e:
        print("Error reading negocios:", e)
        
    try:
        miembros = db.table("miembros_negocio").select("*").eq("usuario_id", user_id).execute()
        print("\nBUSINESS MEMBERSHIPS:")
        print(miembros.data)
    except Exception as e:
        print("Error reading miembros_negocio:", e)

if __name__ == '__main__':
    asyncio.run(main())
