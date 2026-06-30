import sys
sys.path.append('c:\\Users\\Usuario\\Documents\\Workspace\\micro_pymes\\backend')
from app.db.supabase_client import get_supabase_service_client

def main():
    client = get_supabase_service_client()
    user_id = '3fce0a99-76c4-4959-9b70-e7cbfc9c4143'
    try:
        response = client.table("usuarios").select("subscription_status, trial_end, is_exempt, email, nombre").eq("id", user_id).execute()
        print("Response data:", response.data)
    except Exception as e:
        print("Error checking user:", e)

if __name__ == '__main__':
    main()
