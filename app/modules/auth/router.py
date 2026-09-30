"""
Транспортный слой аутентификации (круг 4: Frameworks & Drivers).
"""
from dataclasses import asdict

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.core.dependencies import get_auth_service
from app.core.rate_limit import rate_limit
from app.domain.exceptions import DomainError
from app.http_errors import to_http_exception
from app.modules.auth.service import AuthService
from app.schemas import LoginRequest, RefreshRequest, TokenResponse

router = APIRouter()

# /login и /token делят один счётчик, иначе перебор шёл бы через оба по очереди.
login_limit = Depends(rate_limit(5, 60, scope="login"))


@router.post("/login", response_model=TokenResponse, dependencies=[login_limit])
def login(payload: LoginRequest, service: AuthService = Depends(get_auth_service)):
    try:
        return asdict(service.login(payload.email, payload.password))
    except DomainError as e:
        raise to_http_exception(e)


@router.post(
    "/token",
    response_model=TokenResponse,
    dependencies=[login_limit],
    summary="Login (OAuth2 form, used by Swagger Authorize)",
)
def login_form(
    form: OAuth2PasswordRequestForm = Depends(),
    service: AuthService = Depends(get_auth_service),
):
    try:
        return asdict(service.login(form.username, form.password))
    except DomainError as e:
        raise to_http_exception(e)


@router.post("/refresh", response_model=TokenResponse, dependencies=[Depends(rate_limit(10, 60))])
def refresh(payload: RefreshRequest, service: AuthService = Depends(get_auth_service)):
    try:
        return asdict(service.refresh(payload.refresh_token))
    except DomainError as e:
        raise to_http_exception(e)


@router.post("/logout")
def logout(payload: RefreshRequest, service: AuthService = Depends(get_auth_service)):
    service.logout(payload.refresh_token)
    return {"status": "success"}
