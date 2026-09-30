"""
Зависимости FastAPI для аутентификации (кто ты) и RBAC (какая у тебя роль).
Права на конкретный объект здесь не проверяются: это делают сервисы.
"""
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from app.dependencies import get_auth_repository, get_user_repository
from app.domain.entities import User
from app.domain.exceptions import DomainError
from app.http_errors import to_http_exception
from app.modules.auth.repository import AuthRepository
from app.modules.auth.service import AuthService
from app.modules.users.repository import UserRepository

# tokenUrl ведёт на form-эндпоинт: кнопка Authorize в Swagger шлёт форму, а не JSON.
# auto_error=False, чтобы ответ без токена был в том же формате, что и остальные ошибки.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


def get_auth_service(
    auth_repository: AuthRepository = Depends(get_auth_repository),
    user_repository: UserRepository = Depends(get_user_repository),
) -> AuthService:
    return AuthService(auth_repository, user_repository)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    service: AuthService = Depends(get_auth_service),
) -> User:
    """Пользователь из подписанного access-токена. 401 без токена или с неверным токеном."""
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Требуется аутентификация",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return service.authenticate(token)
    except DomainError as e:
        raise to_http_exception(e)


def require_role(*roles: str):
    """Пропускает только пользователей с одной из перечисленных ролей, иначе 403."""
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Недостаточно прав для этого действия")
        return current_user
    return checker
