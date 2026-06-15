import asyncio
from fastapi import HTTPException

def check():
    try:
        raise HTTPException(status_code=500, detail="This is a test error")
    except Exception as e:
        print(f"Caught: str(e)='{str(e)}', repr(e)='{repr(e)}'")

if __name__ == '__main__':
    check()
