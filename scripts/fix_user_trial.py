import sys
import os
from datetime import datetime, timedelta, timezone

# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import get_supabase_service_client

def fix_users_trial():
    print("=== Iniciando reparación de usuarios en modo prueba ===")
    
    try:
        supabase = get_supabase_service_client()
        
        # 1. Fetch all users (or just those with issues if we could filter by null, 
        # but supabase-py filtering by null is sometimes tricky, let's fetch all)
        print("Obteniendo usuarios...")
        response = supabase.table("usuarios").select("*").execute()
        
        if not response.data:
            print("No se encontraron usuarios.")
            return

        users = response.data
        fixed_count = 0
        
        print(f"Total usuarios encontrados: {len(users)}")
        
        for user in users:
            uid = user.get("id")
            email = user.get("email", "No email")
            status = user.get("subscription_status")
            trial_end = user.get("trial_end")
            
            print(f"Revisando usuario {email} ({uid}): Status={status}, TrialEnd={trial_end}")
            
            # Condition: Status is trial (or None/Empty which defaults to issue?) 
            # actually if None it defaults to 'Forbidden'.
            # The specific error 'Modo de prueba inválido' handles status=='trial' AND not trial_end.
            
            # We will fix anyone who is 'trial' with no date, OR anyone with NO status (set to trial).
            
            needs_fix = False
            
            if status == 'trial' and not trial_end:
                print(f" -> DETECTADO: Usuario en trial sin fecha de fin.")
                needs_fix = True
            elif not status:
                print(f" -> DETECTADO: Usuario sin status de suscripción.")
                needs_fix = True
                
            if needs_fix:
                # Set 30 days from now
                new_end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
                
                update_data = {
                    "subscription_status": "trial",
                    "trial_end": new_end
                }
                
                print(f" -> Aplicando corrección: {update_data}")
                
                upd = supabase.table("usuarios").update(update_data).eq("id", uid).execute()
                
                if upd.data:
                    print(" -> [OK] Usuario corregido exitosamente.")
                    fixed_count += 1
                else:
                    print(" -> [ERROR] Falló la actualización.")
                    
        print(f"\n=== Proceso completado. Usuarios corregidos: {fixed_count} ===")
        
    except Exception as e:
        print(f"\n[ERROR FATAL]: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    fix_users_trial()
