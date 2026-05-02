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
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, password: str = Form(...)):
    """Validate password and set session cookie."""
    if check_password(password):
        response = RedirectResponse(url="/", status_code=303)
        set_session_cookie(response)
        return response

    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Incorrect password."},
        status_code=401,
    )


@router.get("/logout")
async def logout(request: Request):
    """Clear session and redirect to login."""
    response = RedirectResponse(url="/login", status_code=303)
    clear_session_cookie(response)
    return response
