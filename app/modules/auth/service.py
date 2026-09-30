"""
Слой бизнес-логики аутентификации (круги 1 и 2: Entities и Use Cases).
Импорты fastapi и sqlalchemy здесь запрещены.
"""
from app.core.jwt import (
    ACCESS,
    REFRESH,
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    token_fingerprint,
)
from app.core.security import verify_password
from app.domain.entities import TokenPair, User
from app.domain.exceptions import AccessDeniedError, AuthenticationError
from app.modules.auth.repository import AuthRepository
from app.modules.users.repository import UserRepository


class AuthService:
    def __init__(self, auth_repository: AuthRepository, user_repository: UserRepository):
        self.auth_repository = auth_repository
        self.user_repository = user_repository

    def login(self, email: str, password: str) -> TokenPair:
        user = self.user_repository.get_by_email(email)
        # verify_password вызывается и для несуществующего email, чтобы время ответа
        # не выдавало, зарегистрирован ли адрес.
        if not verify_password(password, user.password_hash if user else None) or not user:
            raise AuthenticationError("Неверный email или пароль")
        self._ensure_active(user)
        return self.issue_tokens(user.id)

    def refresh(self, refresh_token: str) -> TokenPair:
        """
        Ротация: старый refresh-токен отзывается, выдаётся новая пара.
        Повторное предъявление отозванного токена означает кражу,
        поэтому отзываются все сессии пользователя.
        """
        try:
            user_id = decode_token(refresh_token, REFRESH)
        except InvalidTokenError:
            raise AuthenticationError("Недействительный refresh-токен")

        record = self.auth_repository.get_refresh_token(token_fingerprint(refresh_token))
        if not record or record.user_id != user_id:
            raise AuthenticationError("Недействительный refresh-токен")

        if record.is_revoked or not self.auth_repository.revoke_refresh_token(record.id):
            self.auth_repository.revoke_all_refresh_tokens(user_id)
            raise AuthenticationError("Refresh-токен уже использован. Все сессии завершены")

        user = self.user_repository.get_by_id(user_id)
        if not user:
            raise AuthenticationError("Пользователь не найден")
        self._ensure_active(user)
        return self.issue_tokens(user.id)

    def logout(self, refresh_token: str) -> None:
        record = self.auth_repository.get_refresh_token(token_fingerprint(refresh_token))
        if record:
            self.auth_repository.revoke_refresh_token(record.id)

    def authenticate(self, access_token: str) -> User:
        """Возвращает пользователя по access-токену. Используется в get_current_user."""
        try:
            user_id = decode_token(access_token, ACCESS)
        except InvalidTokenError:
            raise AuthenticationError("Недействительный или просроченный токен")

        user = self.user_repository.get_by_id(user_id)
        if not user:
            raise AuthenticationError("Пользователь не найден")
        self._ensure_active(user)
        return user

    def issue_tokens(self, user_id: int) -> TokenPair:
        refresh_token, expires_at = create_refresh_token(user_id)
        self.auth_repository.save_refresh_token(user_id, token_fingerprint(refresh_token), expires_at)
        return TokenPair(access_token=create_access_token(user_id), refresh_token=refresh_token)

    @staticmethod
    def _ensure_active(user: User) -> None:
        if user.is_blocked:
            raise AccessDeniedError("Пользователь заблокирован")
