"""Login and logout routes."""

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import check_password, set_session_cookie, clear_session_cookie, get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Show the login form. Redirect to dashboard if already authenticated."""
    if get_current_user(request):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "login.html")


@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, password: str = Form(...)):
    """Validate password and set session cookie.
    
    After 2 failed attempts, redirect to the WordPress honeypot.
    """
    if check_password(password):
        response = RedirectResponse(url="/", status_code=303)
        set_session_cookie(response)
        # Clear fail counter on success
        response.delete_cookie("_fa")
        return response

    # Track failed attempts via cookie
    fail_count = 0
    try:
        fa_cookie = request.cookies.get("_fa", "0")
        fail_count = int(fa_cookie)
    except (ValueError, TypeError):
        fail_count = 0

    fail_count += 1

    if fail_count >= 2:
        # Redirect to honeypot scare page
        response = RedirectResponse(url="/wp-admin", status_code=303)
        response.delete_cookie("_fa")
        return response

    response = templates.TemplateResponse(
        request,
        "login.html",
        context={"error": "Incorrect password."},
        status_code=401,
    )
    response.set_cookie("_fa", str(fail_count), max_age=300, httponly=True)
    return response


@router.get("/logout")
async def logout(request: Request):
    """Clear session and redirect to login."""
    response = RedirectResponse(url="/login", status_code=303)
    clear_session_cookie(response)
    return response
