"""Браузерная сессия: access в памяти клиента, refresh в HttpOnly-cookie."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from app.core.config import settings
from app.core.dependencies import get_auth_service
from app.core.rate_limit import rate_limit
from app.domain.exceptions import DomainError
from app.http_errors import to_http_exception
from app.modules.auth.service import AuthService
from app.schemas import LoginRequest

router = APIRouter()
COOKIE = 'sirius_refresh'


def check_origin(request: Request):
    origin = request.headers.get('origin')
    allowed = {settings.PUBLIC_URL.rstrip('/'), *settings.ALLOWED_ORIGINS}
    if origin not in allowed:
        raise HTTPException(403, 'Недопустимый источник запроса')


def tokens(response, pair):
    response.set_cookie(COOKIE, pair.refresh_token, httponly=True,
                        secure=settings.PUBLIC_URL.startswith('https://'), samesite='lax',
                        max_age=settings.REFRESH_TOKEN_TTL_DAYS * 86400, path='/')
    response.headers['Cache-Control'] = 'no-store'
    return {'access_token': pair.access_token, 'token_type': 'bearer'}


@router.post('/login', dependencies=[Depends(check_origin), Depends(rate_limit(5, 60, scope='login'))])
def login(payload: LoginRequest, response: Response, service: AuthService = Depends(get_auth_service)):
    try:
        return tokens(response, service.login(payload.email, payload.password))
    except DomainError as exc:
        raise to_http_exception(exc)


@router.post('/refresh', dependencies=[Depends(check_origin), Depends(rate_limit(15, 60))])
def refresh(request: Request, response: Response, service: AuthService = Depends(get_auth_service)):
    try:
        return tokens(response, service.refresh(request.cookies.get(COOKIE, '')))
    except DomainError as exc:
        raise to_http_exception(exc)


@router.post('/logout', dependencies=[Depends(check_origin)])
def logout(request: Request, response: Response, service: AuthService = Depends(get_auth_service)):
    service.logout(request.cookies.get(COOKIE, ''))
    response.delete_cookie(COOKIE, path='/')
    return {'status': 'success'}
