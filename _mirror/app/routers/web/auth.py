from typing import Annotated

from fastapi import APIRouter, Form, Request, status, Depends
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import templates
from app.dependencies import get_auth_service
from app.service.auth import AuthService

router = APIRouter()


@router.get(path="/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    if not auth_service.enabled:
        return RedirectResponse(url="/web/general/main")
    return templates.TemplateResponse(
        request=request,
        name="pages/login.html",
        context={},
    )


@router.post(path="/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    username: str = Form(...),
    password: str = Form(...),
):
    if not auth_service.verify_credentials(username, password):
        return templates.TemplateResponse(
            request=request,
            name="pages/login.html",
            context={"error": "Invalid username or password"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    response = RedirectResponse(
        url="/web/general/main",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    auth_service.create_auth_cookie(response, username)
    return response


@router.get(path="/logout", name="logout")
async def logout(auth_service: Annotated[AuthService, Depends(get_auth_service)]):
    response = RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    auth_service.clear_auth_cookie(response)
    return response
