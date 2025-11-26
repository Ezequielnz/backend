import asyncio
import os
import sys
import uuid
from datetime import datetime

# Add backend directory to sys.path
sys.path.append(os.getcwd())

from app.db.supabase_client import get_supabase_client

async def test_insert():
    print("=== Testing Insert into public.usuarios ===")
    supabase = get_supabase_client()
    
    # Generate dummy data
    user_id = str(uuid.uuid4())
    email = f"debug_{user_id[:8]}@example.com"
    
    data = {
        "id": user_id,
        "email": email,
        "nombre": "Debug",
        "apellido": "User",
        "rol": "usuario",
        "creado_en": datetime.now().isoformat(),
        "ultimo_acceso": datetime.now().isoformat()
    }
    
    print(f"Attempting to insert: {data}")
    
    try:
        # Try to insert directly into public.usuarios
        # This mimics what the trigger does
        response = supabase.table("usuarios").insert(data).execute()
        print("Insert successful!")
        print(response.data)
        
        # Cleanup
        print("Cleaning up...")
        supabase.table("usuarios").delete().eq("id", user_id).execute()
        
    except Exception as e:
        print("\n!!! INSERT FAILED !!!")
        print(f"Error: {str(e)}")
        # Try to print more attributes if available
        for attr in ['details', 'hint', 'code', 'message']:
            if hasattr(e, attr):
                print(f"{attr.capitalize()}: {getattr(e, attr)}")

if __name__ == "__main__":
    asyncio.run(test_insert())
