"""
Проверка транспортного слоя: HTTP-статусы и структура ответов совпадают
с MVP-версией. Хранилище подменяется через dependency_overrides.
"""
import pytest
from fastapi.testclient import TestClient

from app import dependencies
from app.domain.entities import OrderStatus
from app.main import app
from app.memory_storage import InMemoryStorage
from app.modules.delivery.repository import InMemoryDeliveryRepository
from app.modules.menu.repository import InMemoryMenuRepository
from app.modules.orders.repository import InMemoryOrderRepository
from app.modules.users.repository import InMemoryUserRepository


@pytest.fixture
def storage():
    storage = InMemoryStorage()
    app.dependency_overrides = {
        dependencies.get_user_repository: lambda: InMemoryUserRepository(storage),
        dependencies.get_menu_repository: lambda: InMemoryMenuRepository(storage),
        dependencies.get_order_repository: lambda: InMemoryOrderRepository(storage),
        dependencies.get_delivery_repository: lambda: InMemoryDeliveryRepository(storage),
    }
    yield storage
    app.dependency_overrides = {}


@pytest.fixture
def client(storage):
    return TestClient(app)


def test_full_order_flow(client, storage):
    response = client.post("/users/register", json={"email": "student@sirius.ru", "phone": "89991234567"})
    assert response.status_code == 200
    user_id = response.json()["user_id"]
    assert response.json() == {"status": "success", "user_id": user_id, "email": "student@sirius.ru"}

    response = client.post(f"/users/{user_id}/topup", params={"amount": 1000})
    assert response.json() == {"status": "success", "new_balance": 1000.0}

    item_id = client.post("/menu/items", json={"name": "Плов", "price": 150}).json()["item_id"]

    response = client.post("/orders/create", json={"user_id": user_id, "item_id": item_id, "quantity": 2})
    assert response.status_code == 200
    order_id = response.json()["order_id"]
    assert response.json() == {"status": "success", "order_id": order_id}
    assert storage.users[user_id].balance == 700

    storage.orders[order_id].status = OrderStatus.PAID
    courier_id = client.post("/users/register", json={"email": "courier@sirius.ru"}).json()["user_id"]
    response = client.post("/delivery/assign", json={"order_id": order_id, "courier_id": courier_id})
    delivery_id = response.json()["delivery_id"]
    assert response.json() == {"status": "success", "delivery_id": delivery_id}

    assert client.patch(f"/delivery/{delivery_id}/complete").json() == {"status": "success"}
    assert storage.orders[order_id].status == OrderStatus.DELIVERED


@pytest.mark.parametrize(
    ("method", "url", "body", "status", "detail"),
    [
        ("post", "/orders/create", {"user_id": 1, "item_id": 1, "quantity": 0}, 400, "Количество должно быть больше нуля"),
        ("post", "/orders/create", {"user_id": 999, "item_id": 1, "quantity": 1}, 404, "Пользователь не найден"),
        ("post", "/users/999/topup?amount=10", None, 404, "Пользователь не найден"),
        ("post", "/users/1/topup?amount=0", None, 400, "Сумма пополнения должна быть положительной"),
        ("post", "/menu/items", {"name": "X", "price": 10}, 400, "Название блюда слишком короткое"),
        ("patch", "/menu/items/999", {"name": "Щи"}, 404, "Блюдо не найдено"),
        ("post", "/delivery/assign", {"order_id": 999, "courier_id": 1}, 404, "Заказ не найден"),
        ("patch", "/delivery/999/complete", None, 404, "Доставка не найдена"),
    ],
)
def test_errors_keep_mvp_status_codes(client, method, url, body, status, detail):
    response = client.request(method, url, json=body)

    assert response.status_code == status
    assert response.json() == {"detail": detail}


def test_blocked_user_gets_403(client, storage):
    user_id = client.post("/users/register", json={"email": "student@sirius.ru"}).json()["user_id"]
    storage.users[user_id].is_blocked = True

    response = client.post(f"/users/{user_id}/topup", params={"amount": 10})

    assert response.status_code == 403
