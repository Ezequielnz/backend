import sys
import asyncio
from fastapi import Request
from fastapi.datastructures import Headers

sys.path.append('c:\\Users\\Usuario\\Documents\\Workspace\\micro_pymes\\backend')
from app.services.subscription_guard import check_subscription
from app.db.supabase_client import get_supabase_service_client

class MockUser:
    def __init__(self, id):
        self.id = id

async def main():
    db = get_supabase_service_client()
    class MockRequest:
        def __init__(self):
            self.headers = Headers()
            self.state = type('State', (), {})()
            
    req = MockRequest()
    user = MockUser('3fce0a99-76c4-4959-9b70-e7cbfc9c4143')
    
    try:
        res = await check_subscription(request=req, current_user=user, db=db)
        print("RESULT (allowed):", res)
    except Exception as e:
        print("EXCEPTION RAISED:", type(e), str(e))
        if hasattr(e, 'status_code'):
            print("STATUS CODE:", e.status_code)
            print("DETAIL:", e.detail)

if __name__ == '__main__':
    asyncio.run(main())
