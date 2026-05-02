"""Single-password session authentication.

No user accounts, no signup, no OAuth. One password from env, one session cookie.
"""

from functools import wraps
from typing import Optional

from fastapi import Request, Response, HTTPException
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.config import settings

# Session cookie config
COOKIE_NAME = "ta_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days

_serializer = URLSafeTimedSerializer(settings.secret_key)


def create_session_token() -> str:
    """Create a signed session token."""
    return _serializer.dumps({"authenticated": True})


def verify_session_token(token: str) -> bool:
    """Verify a session token is valid and not expired."""
    try:
        data = _serializer.loads(token, max_age=COOKIE_MAX_AGE)
        return data.get("authenticated", False)
    except (BadSignature, SignatureExpired):
        return False


def check_password(password: str) -> bool:
    """Check if the provided password matches the configured dashboard password."""
    return password == settings.dashboard_password


def get_current_user(request: Request) -> bool:
    """Check if the current request has a valid session. Returns True or False."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False
    return verify_session_token(token)


def set_session_cookie(response: Response) -> Response:
    """Set the session cookie on a response."""
    token = create_session_token()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return response


def clear_session_cookie(response: Response) -> Response:
    """Clear the session cookie."""
    response.delete_cookie(key=COOKIE_NAME)
    return response


def require_auth(request: Request) -> Optional[RedirectResponse]:
    """Check auth and return a redirect to login if not authenticated.
    Returns None if authenticated.
    """
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)
    return None
