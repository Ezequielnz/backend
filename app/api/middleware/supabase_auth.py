from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseFunction
from starlette.requests import Request
from starlette.responses import Response
from fastapi import HTTPException
from fastapi.logger import logger # For logging

from app.db.supabase_client import get_supabase_client, supabase_client as sb_direct_client # Access to the initialized client
from supabase.lib.client_options import ClientOptions
from gotrue.errors import AuthApiError

class SupabaseAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseFunction) -> Response:
        request.state.supabase_user = None
        auth_header = request.headers.get("Authorization")

        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]
                try:
                    # Ensure the client is initialized.
                    # Using the direct client instance if available and initialized,
                    # otherwise, get_supabase_client() will attempt initialization or raise error.
                    client = sb_direct_client
                    if client is None:
                        # This condition might occur if the app starts and this middleware is hit
                        # before get_supabase_client() has been called elsewhere to initialize.
                        # Or if SUPABASE_URL/KEY were missing at startup.
                        logger.warning("Supabase client not initialized at middleware entry. Attempting initialization.")
                        client = get_supabase_client() # This will raise ConnectionError if still not initializable

                    # Validate the token
                    user_response = await client.auth.get_user(token) # Use await for async version
                    if user_response and user_response.user:
                        request.state.supabase_user = user_response.user
                        # logger.debug(f"Supabase user set in request.state: {user_response.user.id}")
                except AuthApiError as e:
                    # This handles specific Supabase auth errors (e.g., invalid token, expired token)
                    # logger.warning(f"Supabase AuthApiError: {e.message} (Status: {e.status})")
                    # We don't raise HTTPException here; dependencies will handle it.
                    pass
                except ConnectionError as e:
                    # Raised by get_supabase_client() if client cannot be initialized
                    logger.error(f"Supabase connection error in middleware: {e}")
                    # Potentially, you might want to return a 503 Service Unavailable here,
                    # but for now, let it proceed, and dependencies will fail.
                    pass
                except Exception as e:
                    # Catch any other unexpected errors during token validation
                    # logger.error(f"Unexpected error during Supabase token validation: {e}")
                    pass
            # else:
                # logger.debug("Authorization header format incorrect.")
        # else:
            # logger.debug("No Authorization header found.")

        response = await call_next(request)
        return response
