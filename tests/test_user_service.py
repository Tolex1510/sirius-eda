import pytest

from app.domain.exceptions import AccessDeniedError, BusinessRuleError, NotFoundError
from app.modules.users.repository import InMemoryUserRepository
from app.modules.users.service import UserService
from tests.conftest import add_user


@pytest.fixture
def service(storage) -> UserService:
    return UserService(InMemoryUserRepository(storage))


def test_register_creates_user_with_zero_balance(service):
    user = service.register("student@sirius.ru", "89991234567")

    assert user.id is not None
    assert user.balance == 0.0
    assert user.is_blocked is False


def test_register_rejects_duplicate_email(service):
    service.register("student@sirius.ru", None)

    with pytest.raises(BusinessRuleError, match="уже зарегистрирован"):
        service.register("student@sirius.ru", None)


def test_top_up_increases_balance(service, storage):
    user = add_user(storage, balance=100)

    assert service.top_up_balance(user.id, 250) == 350
    assert storage.users[user.id].balance == 350


def test_top_up_unknown_user(service):
    with pytest.raises(NotFoundError):
        service.top_up_balance(999, 100)


def test_top_up_blocked_user(service, storage):
    user = add_user(storage, is_blocked=True)

    with pytest.raises(AccessDeniedError, match="заблокирован"):
        service.top_up_balance(user.id, 100)


def test_top_up_limit(service, storage):
    user = add_user(storage)

    assert service.top_up_balance(user.id, 50000) == 50000
    with pytest.raises(BusinessRuleError, match="50000"):
        service.top_up_balance(user.id, 50000.01)
