import sys
import asyncio
sys.path.append('c:\\Users\\Usuario\\Documents\\Workspace\\micro_pymes\\backend')
from app.db.supabase_client import get_supabase_service_client

async def main():
    db = get_supabase_service_client()
    user_id = '3fce0a99-76c4-4959-9b70-e7cbfc9c4143'
    
    user_res = db.table("usuarios").select("*").eq("id", user_id).execute()
    print("USER DATA:")
    print(user_res.data)
    
    user_negocios = db.table("usuarios_negocios").select("*").eq("usuario_id", user_id).execute()
    print("USER NEGOCIOS:")
    print(user_negocios.data)

if __name__ == '__main__':
    asyncio.run(main())
