"""
Хеширование паролей через bcrypt.
passlib из методички не обновлялся с 2020 года и ломается на bcrypt 4.1+,
поэтому библиотека bcrypt используется напрямую.
"""
import bcrypt

from app.core.config import settings

# bcrypt учитывает только первые 72 байта пароля, более длинные отклоняются заранее.
MAX_PASSWORD_BYTES = 72

# Хеш для сравнения, когда пользователь не найден: время ответа не выдаёт,
# существует ли email.
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt(settings.BCRYPT_ROUNDS)).decode()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(settings.BCRYPT_ROUNDS)).decode()


def verify_password(plain: str, hashed: str | None) -> bool:
    candidate = plain.encode()
    if hashed is None or len(candidate) > MAX_PASSWORD_BYTES:
        bcrypt.checkpw(candidate[:MAX_PASSWORD_BYTES], _DUMMY_HASH.encode())
        return False
    return bcrypt.checkpw(candidate, hashed.encode())
