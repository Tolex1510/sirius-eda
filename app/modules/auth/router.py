"""
Транспортный слой аутентификации (круг 4: Frameworks & Drivers).
"""
import secrets
from dataclasses import asdict
from datetime import timedelta
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm

from app.core.config import settings
from app.core.dependencies import get_auth_service
from app.core.jwt import InvalidTokenError, read_signed_payload, sign_payload
from app.core.rate_limit import rate_limit
from app.domain.exceptions import DomainError
from app.http_errors import to_http_exception
from app.modules.auth.oauth import GoogleOAuthProvider, OAuthProvider, new_pkce_pair
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


OAUTH_COOKIE = "oauth_google"
OAUTH_STATE_TYPE = "oauth_state"
OAUTH_STATE_TTL = timedelta(minutes=10)


@lru_cache
def _google_provider() -> GoogleOAuthProvider:
    return GoogleOAuthProvider(settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET, settings.GOOGLE_REDIRECT_URI)


def get_google_provider() -> OAuthProvider:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Вход через Google не настроен")
    return _google_provider()


oauth_limit = Depends(rate_limit(10, 60, scope="oauth-google"))


@router.get(
    "/google/login",
    dependencies=[oauth_limit],
    summary="Login with Google (open in a browser, not in Swagger)",
)
def google_login(provider: OAuthProvider = Depends(get_google_provider)):
    state = secrets.token_urlsafe(32)
    code_verifier, code_challenge = new_pkce_pair()

    response = RedirectResponse(provider.authorization_url(state, code_challenge), status_code=302)
    # state и verifier живут в подписанной HttpOnly-cookie этого браузера.
    # Callback сверяет state из URL с cookie: чужой code, подсунутый по ссылке (login CSRF), не пройдёт.
    response.set_cookie(
        OAUTH_COOKIE,
        sign_payload({"state": state, "verifier": code_verifier}, OAUTH_STATE_TYPE, OAUTH_STATE_TTL),
        max_age=int(OAUTH_STATE_TTL.total_seconds()),
        httponly=True,
        secure=not settings.DEBUG,
        # Lax, а не Strict: иначе браузер не отправит cookie при переходе с accounts.google.com.
        samesite="lax",
        path="/auth/google",
    )
    return response


@router.get("/google/callback", response_model=TokenResponse, dependencies=[oauth_limit])
def google_callback(
    request: Request,
    response: Response,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    provider: OAuthProvider = Depends(get_google_provider),
    service: AuthService = Depends(get_auth_service),
):
    if error:
        raise HTTPException(status_code=401, detail="Вход через Google отменён")

    cookie = request.cookies.get(OAUTH_COOKIE)
    if not code or not state or not cookie:
        raise HTTPException(status_code=400, detail="Некорректный ответ провайдера")

    try:
        saved = read_signed_payload(cookie, OAUTH_STATE_TYPE)
    except InvalidTokenError:
        raise HTTPException(status_code=400, detail="Сессия входа истекла, начните заново")

    if not secrets.compare_digest(saved["state"], state):
        raise HTTPException(status_code=400, detail="Параметр state не совпадает")

    try:
        tokens = service.login_with_provider(provider, code, saved["verifier"])
    except DomainError as e:
        raise to_http_exception(e)

    response.delete_cookie(OAUTH_COOKIE, path="/auth/google")
    return asdict(tokens)
