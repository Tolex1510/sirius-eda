"""
Выпуск и проверка JWT. Используется PyJWT: у python-jose из методички
есть неисправленные уязвимости (CVE-2024-33663, CVE-2024-33664).
"""
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings

ALGORITHM = "HS256"
ACCESS = "access"
REFRESH = "refresh"
# Монолит вызывает внутренние сервисы от имени пользователя. Отдельный тип:
# такой токен не примет публичный API, а пользовательский не примет сервис.
INTERNAL = "internal"


class InvalidTokenError(Exception):
    pass


def _encode(user_id: int, token_type: str, ttl: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
        # Без jti два токена, выданные в одну секунду, совпали бы.
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user_id: int) -> str:
    return _encode(user_id, ACCESS, timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES))


def create_internal_token(user_id: int) -> str:
    # Сервис проверяет токен в начале вызова, поэтому минуты хватает даже долгому стриму.
    return _encode(user_id, INTERNAL, timedelta(minutes=1))


def create_refresh_token(user_id: int) -> tuple[str, datetime]:
    ttl = timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS)
    return _encode(user_id, REFRESH, ttl), datetime.now(UTC) + ttl


def decode_token(token: str, expected_type: str) -> int:
    """Проверяет подпись, срок и тип токена. Возвращает id пользователя."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp", "type"]},
        )
        if payload["type"] != expected_type:
            raise InvalidTokenError()
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError) as e:
        raise InvalidTokenError() from e


def token_fingerprint(token: str) -> str:
    """SHA-256 токена для хранения в БД. bcrypt не нужен: токен и так случайный и длинный."""
    return hashlib.sha256(token.encode()).hexdigest()


def sign_payload(payload: dict, token_type: str, ttl: timedelta) -> str:
    """Подписанный короткоживущий контейнер для служебных данных, например state OAuth."""
    return jwt.encode(
        {**payload, "type": token_type, "exp": datetime.now(UTC) + ttl},
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )


def read_signed_payload(token: str, token_type: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM], options={"require": ["exp", "type"]})
    except jwt.PyJWTError as e:
        raise InvalidTokenError() from e
    if payload["type"] != token_type:
        raise InvalidTokenError()
    return payload
