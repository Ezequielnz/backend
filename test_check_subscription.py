import sys
import asyncio
from fastapi import Request
from fastapi.datastructures import Headers

sys.path.append('c:\\Users\\Usuario\\Documents\Workspace\\micro_pymes\\backend')
from app.services.subscription_guard import check_subscription
from app.db.supabase_client import get_supabase_service_client

class MockUser:
    def __init__(self, id, email=None):
        self.id = id
        self.email = email

class MockRequest:
    def __init__(self, method="GET"):
        self.headers = Headers()
        self.state = type('State', (), {})()
        self.method = method

class FailingDBTable:
    def select(self, *args, **kwargs):
        return self
    def eq(self, *args, **kwargs):
        return self
    def limit(self, *args, **kwargs):
        return self
    def execute(self):
        raise Exception("Connection lost to database cluster")

class FailingDB:
    def table(self, table_name):
        return FailingDBTable()

async def run_test(user_id, email, method, db_client=None):
    if db_client is None:
        db_client = get_supabase_service_client()
    req = MockRequest(method=method)
    user = MockUser(user_id, email=email)
    
    print(f"\n--- Running test: User ID={user_id}, Email={email}, Method={method}, DB={'Normal' if db_client is not FailingDB() else 'Failing'} ---")
    try:
        res = await check_subscription(request=req, current_user=user, db=db_client)
        print("RESULT: Access Allowed")
    except Exception as e:
        print("EXCEPTION RAISED:", type(e), str(e))
        if hasattr(e, 'status_code'):
            print("STATUS CODE:", e.status_code)
            print("DETAIL:", e.detail)

async def main():
    # 1. Test exempt user GET
    await run_test('ac3b9419-972d-4e6b-921b-ef2cc5411c98', 'ezequieln085@gmail.com', 'GET')
    
    # 2. Test exempt user POST
    await run_test('ac3b9419-972d-4e6b-921b-ef2cc5411c98', 'ezequieln085@gmail.com', 'POST')
    
    # 3. Test normal user GET (trial expired, but GET is read-only)
    await run_test('d2dcbbdc-549f-4663-86d8-5902590bfb91', 'maximilianonunez145@gmail.com', 'GET')
    
    # 4. Test normal user POST (should block since subscription is not active and trial expired)
    await run_test('d2dcbbdc-549f-4663-86d8-5902590bfb91', 'maximilianonunez145@gmail.com', 'POST')
    
    # 5. Test failing DB on GET (should allow access read-only)
    await run_test('d2dcbbdc-549f-4663-86d8-5902590bfb91', 'maximilianonunez145@gmail.com', 'GET', db_client=FailingDB())
    
    # 6. Test failing DB on POST (should raise 500)
    await run_test('d2dcbbdc-549f-4663-86d8-5902590bfb91', 'maximilianonunez145@gmail.com', 'POST', db_client=FailingDB())

if __name__ == '__main__':
    asyncio.run(main())
