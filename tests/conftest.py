import os

# Тесты не требуют ни PostgreSQL, ни Redis, ни файла .env.
os.environ.setdefault("REPOSITORY_BACKEND", "memory")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-for-hs256")
os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@localhost:1/unused")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("BCRYPT_ROUNDS", "4")

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.domain.entities import Delivery, MenuItem, Order, Role, User
from app.memory_storage import InMemoryStorage
from app.modules.orders.notifier import OrderNotifier


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


class RecordingNotifier(OrderNotifier):
    """Запоминает события вместо PDF, email и SMS."""

    def __init__(self):
        self.created: list[tuple[int, int]] = []

    def order_created(self, order_id: int, customer: User) -> None:
        self.created.append((order_id, customer.id))


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


def add_user(
    storage: InMemoryStorage,
    balance: float = 0.0,
    is_blocked: bool = False,
    role: str = Role.STUDENT,
    password_hash: str | None = None,
) -> User:
    user_id = storage.next_id("users")
    user = User(
        id=user_id,
        email=f"user{user_id}@sirius.ru",
        phone=None,
        balance=balance,
        is_blocked=is_blocked,
        role=role,
        password_hash=password_hash,
    )
    storage.users[user_id] = user
    return user


def add_menu_item(storage: InMemoryStorage, price: float = 100.0, is_available: bool = True) -> MenuItem:
    item_id = storage.next_id("menu_items")
    item = MenuItem(id=item_id, name=f"Блюдо {item_id}", price=price, is_available=is_available)
    storage.menu_items[item_id] = item
    return item


def add_order(storage: InMemoryStorage, user_id: int, item_id: int, status: str, total_cost: float = 100.0) -> Order:
    order_id = storage.next_id("orders")
    order = Order(id=order_id, user_id=user_id, item_id=item_id, quantity=1, status=status, total_cost=total_cost)
    storage.orders[order_id] = order
    return order


def add_delivery(storage: InMemoryStorage, order_id: int, courier_id: int, status: str) -> Delivery:
    delivery_id = storage.next_id("deliveries")
    delivery = Delivery(id=delivery_id, order_id=order_id, courier_id=courier_id, status=status)
    storage.deliveries[delivery_id] = delivery
    return delivery


@pytest.fixture
def client(storage, notifier):
    """
    Приложение целиком, но на in-memory хранилище и fakeredis.
    Хранилище общее с фикстурой storage, чтобы тест мог менять данные напрямую.
    """
    from app import dependencies
    from app.core.rate_limit import get_redis
    from app.main import app
    from app.modules.auth.repository import InMemoryAuthRepository
    from app.modules.delivery.repository import InMemoryDeliveryRepository
    from app.modules.menu.repository import InMemoryMenuRepository
    from app.modules.orders.repository import InMemoryOrderRepository
    from app.modules.users.repository import InMemoryUserRepository

    redis = fakeredis.FakeRedis()
    app.dependency_overrides = {
        dependencies.get_user_repository: lambda: InMemoryUserRepository(storage),
        dependencies.get_menu_repository: lambda: InMemoryMenuRepository(storage),
        dependencies.get_order_repository: lambda: InMemoryOrderRepository(storage),
        dependencies.get_order_notifier: lambda: notifier,
        dependencies.get_delivery_repository: lambda: InMemoryDeliveryRepository(storage),
        dependencies.get_auth_repository: lambda: InMemoryAuthRepository(storage),
        get_redis: lambda: redis,
    }
    yield TestClient(app)
    app.dependency_overrides = {}


def create_account(client: TestClient, storage: InMemoryStorage, role: str = Role.STUDENT, balance: float = 0.0):
    """Регистрирует пользователя через API, выставляет роль и баланс, возвращает (id, заголовки)."""
    email = f"user{storage.next_id('emails')}@sirius.ru"
    user_id = client.post("/users/register", json={"email": email, "password": "password123"}).json()["user_id"]
    storage.users[user_id].role = role
    storage.users[user_id].balance = balance
    token = client.post("/auth/login", json={"email": email, "password": "password123"}).json()["access_token"]
    return user_id, {"Authorization": f"Bearer {token}"}
