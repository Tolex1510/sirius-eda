import pytest

from app.core.security import verify_password
from app.domain.entities import Role
from app.domain.exceptions import AccessDeniedError, BusinessRuleError, NotFoundError
from app.modules.users.repository import InMemoryUserRepository
from app.modules.users.service import UserService
from tests.conftest import add_user


@pytest.fixture
def service(storage) -> UserService:
    return UserService(InMemoryUserRepository(storage))


def test_register_creates_student_with_hashed_password(service):
    user = service.register("student@sirius.ru", "password123", "89991234567")

    assert user.balance == 0.0
    assert user.role == Role.STUDENT
    assert user.password_hash != "password123"
    assert user.password_hash.startswith("$2b$")
    assert verify_password("password123", user.password_hash)


def test_register_rejects_duplicate_email(service):
    service.register("student@sirius.ru", "password123")

    with pytest.raises(BusinessRuleError, match="уже зарегистрирован"):
        service.register("student@sirius.ru", "password456")


def test_top_up_own_balance(service, storage):
    user = add_user(storage, balance=100)

    assert service.top_up_balance(user.id, 250, actor=user) == 350
    assert storage.users[user.id].balance == 350


def test_top_up_foreign_balance_is_forbidden(service, storage):
    owner = add_user(storage, balance=100)
    stranger = add_user(storage)

    with pytest.raises(AccessDeniedError, match="чужому аккаунту"):
        service.top_up_balance(owner.id, 10, actor=stranger)
    assert storage.users[owner.id].balance == 100


def test_admin_can_top_up_anyone(service, storage):
    owner = add_user(storage)
    admin = add_user(storage, role=Role.ADMIN)

    assert service.top_up_balance(owner.id, 10, actor=admin) == 10


def test_top_up_unknown_user_by_admin(service, storage):
    admin = add_user(storage, role=Role.ADMIN)

    with pytest.raises(NotFoundError):
        service.top_up_balance(999, 100, actor=admin)


def test_top_up_blocked_user(service, storage):
    user = add_user(storage, is_blocked=True)

    with pytest.raises(AccessDeniedError, match="заблокирован"):
        service.top_up_balance(user.id, 100, actor=user)


def test_top_up_limit(service, storage):
    user = add_user(storage)

    assert service.top_up_balance(user.id, 50000, actor=user) == 50000
    with pytest.raises(BusinessRuleError, match="50000"):
        service.top_up_balance(user.id, 50000.01, actor=user)


def test_change_role(service, storage):
    user = add_user(storage)

    assert service.change_role(user.id, Role.COOK).role == Role.COOK
    with pytest.raises(BusinessRuleError):
        service.change_role(user.id, "superuser")
