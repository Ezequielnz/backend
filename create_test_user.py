import sys
sys.path.append('c:\\Users\\Usuario\\Documents\\Workspace\\micro_pymes\\backend')
from app.db.supabase_client import get_supabase_service_client

def main():
    client = get_supabase_service_client()
    email = "test_trial_expired_999@example.com"
    password = "Password123!"
    
    print("Creating user via auth.admin...")
    try:
        # Create user with confirmed email
        auth_response = client.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True
        })
        
        user = auth_response.user
        user_id = user.id
        print(f"User created successfully! ID: {user_id}")
        
        # Now update the user's row in the 'usuarios' table
        # If the trigger created it, we can update it. If not, we might need to insert it.
        # Let's check if it exists in 'usuarios' table first.
        import time
        time.sleep(2) # Wait for any trigger to run
        
        user_row = client.table("usuarios").select("*").eq("id", user_id).execute()
        if user_row.data:
            print("User row exists in 'usuarios' table. Updating status...")
            update_res = client.table("usuarios").update({
                "subscription_status": "trial_expired",
                "is_exempt": False,
                "nombre": "Test",
                "apellido": "Expired"
            }).eq("id", user_id).execute()
            print("Update result:", update_res.data)
        else:
            print("User row does NOT exist in 'usuarios' table. Inserting row...")
            insert_res = client.table("usuarios").insert({
                "id": user_id,
                "email": email,
                "subscription_status": "trial_expired",
                "is_exempt": False,
                "nombre": "Test",
                "apellido": "Expired"
            }).execute()
            print("Insert result:", insert_res.data)
            
    except Exception as e:
        print("Error during user creation:", e)

if __name__ == '__main__':
    main()
