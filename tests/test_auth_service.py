from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.jwt import ALGORITHM, create_access_token, create_refresh_token
from app.core.security import hash_password
from app.domain.exceptions import AccessDeniedError, AuthenticationError
from app.modules.auth.repository import InMemoryAuthRepository
from app.modules.auth.service import AuthService
from app.modules.users.repository import InMemoryUserRepository
from tests.conftest import add_user

PASSWORD = "correct-horse-battery"


@pytest.fixture
def service(storage) -> AuthService:
    return AuthService(InMemoryAuthRepository(storage), InMemoryUserRepository(storage))


@pytest.fixture
def user(storage):
    return add_user(storage, password_hash=hash_password(PASSWORD))


def test_login_returns_working_tokens(service, user):
    tokens = service.login(user.email, PASSWORD)

    assert tokens.token_type == "bearer"
    assert service.authenticate(tokens.access_token).id == user.id


@pytest.mark.parametrize("email, password", [("user1@sirius.ru", "wrong"), ("nobody@sirius.ru", PASSWORD)])
def test_login_failure_does_not_reveal_which_part_is_wrong(service, user, email, password):
    with pytest.raises(AuthenticationError, match="Неверный email или пароль"):
        service.login(email, password)


def test_user_without_password_cannot_login(service, storage):
    oauth_only = add_user(storage)

    with pytest.raises(AuthenticationError):
        service.login(oauth_only.email, "")


def test_blocked_user_cannot_login(service, storage):
    blocked = add_user(storage, is_blocked=True, password_hash=hash_password(PASSWORD))

    with pytest.raises(AccessDeniedError):
        service.login(blocked.email, PASSWORD)


def test_refresh_token_is_not_an_access_token(service, user):
    tokens = service.login(user.email, PASSWORD)

    with pytest.raises(AuthenticationError):
        service.authenticate(tokens.refresh_token)


def test_expired_access_token_is_rejected(service, user):
    expired = jwt.encode(
        {"sub": str(user.id), "type": "access", "exp": datetime.now(UTC) - timedelta(seconds=1)},
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )

    with pytest.raises(AuthenticationError):
        service.authenticate(expired)


def test_token_signed_with_other_key_is_rejected(service, user):
    forged = jwt.encode(
        {"sub": str(user.id), "type": "access", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        "attacker-key-attacker-key-attacker-key",
        algorithm=ALGORITHM,
    )

    with pytest.raises(AuthenticationError):
        service.authenticate(forged)


def test_unsigned_token_is_rejected(service, user):
    unsigned = jwt.encode({"sub": str(user.id), "type": "access", "exp": 9999999999}, None, algorithm="none")

    with pytest.raises(AuthenticationError):
        service.authenticate(unsigned)


def test_refresh_rotates_tokens(service, storage, user):
    first = service.login(user.email, PASSWORD)

    second = service.refresh(first.refresh_token)

    assert second.refresh_token != first.refresh_token
    assert service.authenticate(second.access_token).id == user.id
    assert sum(not r.is_revoked for r in storage.refresh_tokens.values()) == 1


def test_reused_refresh_token_revokes_all_sessions(service, storage, user):
    stolen = service.login(user.email, PASSWORD)
    other_device = service.login(user.email, PASSWORD)
    service.refresh(stolen.refresh_token)

    with pytest.raises(AuthenticationError, match="Все сессии завершены"):
        service.refresh(stolen.refresh_token)

    assert all(r.is_revoked for r in storage.refresh_tokens.values())
    with pytest.raises(AuthenticationError):
        service.refresh(other_device.refresh_token)


def test_refresh_token_not_issued_by_server_is_rejected(service, user):
    token, _ = create_refresh_token(user.id)

    with pytest.raises(AuthenticationError):
        service.refresh(token)


def test_access_token_cannot_be_used_to_refresh(service, user):
    with pytest.raises(AuthenticationError):
        service.refresh(create_access_token(user.id))


def test_logout_revokes_refresh_token(service, user):
    tokens = service.login(user.email, PASSWORD)

    service.logout(tokens.refresh_token)

    with pytest.raises(AuthenticationError):
        service.refresh(tokens.refresh_token)


def test_blocked_after_login_loses_access(service, storage, user):
    tokens = service.login(user.email, PASSWORD)
    storage.users[user.id].is_blocked = True

    with pytest.raises(AccessDeniedError):
        service.authenticate(tokens.access_token)
