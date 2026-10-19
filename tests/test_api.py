"""
Транспортный слой: для авторизованных пользователей структура ответов
и HTTP-статусы остались как в лабораторной работе № 2.
"""
import pytest

from app.domain.entities import OrderStatus, Role
from tests.conftest import create_account


def test_register_response_is_unchanged(client):
    response = client.post("/users/register", json={"email": "student@sirius.ru", "password": "password123"})

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "success", "user_id": body["user_id"], "email": "student@sirius.ru"}


def test_full_order_flow(client, storage, notifier):
    student_id, student = create_account(client, storage)
    _, cook = create_account(client, storage, Role.COOK)
    courier_id, courier = create_account(client, storage, Role.COURIER)

    response = client.post(f"/users/{student_id}/topup", params={"amount": 1000}, headers=student)
    assert response.json() == {"status": "success", "new_balance": 1000.0}

    item_id = client.post("/menu/items", json={"name": "Плов", "price": 150}, headers=cook).json()["item_id"]
    assert [i["name"] for i in client.get("/menu/items").json()] == ["Плов"]

    response = client.post("/orders/create", json={"item_id": item_id, "quantity": 2}, headers=student)
    assert response.status_code == 200
    order_id = response.json()["order_id"]
    assert response.json() == {"status": "success", "order_id": order_id}
    assert storage.users[student_id].balance == 700
    assert storage.orders[order_id].user_id == student_id
    assert notifier.created == [(order_id, student_id)]

    assert [o["id"] for o in client.get("/kitchen/orders", headers=cook).json()] == [order_id]
    assert [o["id"] for o in client.get("/orders/my", headers=student).json()] == [order_id]

    storage.orders[order_id].status = OrderStatus.PAID
    response = client.post("/delivery/assign", json={"order_id": order_id, "courier_id": courier_id}, headers=courier)
    delivery_id = response.json()["delivery_id"]
    assert response.json() == {"status": "success", "delivery_id": delivery_id}
    assert client.get(f"/delivery/{delivery_id}", headers=student).status_code == 200

    response = client.patch(f"/delivery/{delivery_id}/complete", headers=courier)
    assert response.json() == {"status": "success"}
    assert storage.orders[order_id].status == OrderStatus.DELIVERED


def test_cancel_refunds_balance(client, storage):
    _, student = create_account(client, storage, balance=500)
    _, cook = create_account(client, storage, Role.COOK)
    item_id = client.post("/menu/items", json={"name": "Суп", "price": 100}, headers=cook).json()["item_id"]
    order_id = client.post("/orders/create", json={"item_id": item_id, "quantity": 1}, headers=student).json()["order_id"]

    assert client.post(f"/orders/{order_id}/cancel", headers=student).json() == {"status": "success"}
    assert client.get("/users/me", headers=student).json()["balance"] == 500


def test_order_payload_user_id_is_ignored(client, storage):
    student_id, student = create_account(client, storage, balance=500)
    victim_id, _ = create_account(client, storage, balance=500)
    _, cook = create_account(client, storage, Role.COOK)
    item_id = client.post("/menu/items", json={"name": "Суп", "price": 100}, headers=cook).json()["item_id"]

    order_id = client.post(
        "/orders/create",
        json={"user_id": victim_id, "item_id": item_id, "quantity": 1},
        headers=student,
    ).json()["order_id"]

    assert storage.orders[order_id].user_id == student_id
    assert storage.users[victim_id].balance == 500


@pytest.mark.parametrize(
    ("method", "url", "body", "role", "status", "detail"),
    [
        ("post", "/orders/create", {"item_id": 1, "quantity": 0}, Role.STUDENT, 400, "Количество должно быть больше нуля"),
        ("post", "/orders/create", {"item_id": 999, "quantity": 1}, Role.STUDENT, 404, "Блюдо не найдено"),
        ("post", "/users/999/topup?amount=10", None, Role.ADMIN, 404, "Пользователь не найден"),
        ("post", "/users/1/topup?amount=0", None, Role.STUDENT, 400, "Сумма пополнения должна быть положительной"),
        ("post", "/menu/items", {"name": "X", "price": 10}, Role.COOK, 400, "Название блюда слишком короткое"),
        ("patch", "/menu/items/999", {"name": "Щи"}, Role.COOK, 404, "Блюдо не найдено"),
        ("post", "/delivery/assign", {"order_id": 999, "courier_id": 1}, Role.ADMIN, 404, "Заказ не найден"),
        ("patch", "/delivery/999/complete", None, Role.COURIER, 404, "Доставка не найдена"),
    ],
)
def test_errors_keep_status_codes(client, storage, method, url, body, role, status, detail):
    _, headers = create_account(client, storage, role)

    response = client.request(method, url, json=body, headers=headers)

    assert response.status_code == status
    assert response.json() == {"detail": detail}


def test_swagger_authorize_form_login(client, storage):
    client.post("/users/register", json={"email": "form@sirius.ru", "password": "password123"})

    response = client.post("/auth/token", data={"username": "form@sirius.ru", "password": "password123"})

    assert response.status_code == 200
    token = response.json()["access_token"]
    assert client.get("/users/me", headers={"Authorization": f"Bearer {token}"}).json()["email"] == "form@sirius.ru"


def test_refresh_endpoint_rotates(client, storage):
    client.post("/users/register", json={"email": "r@sirius.ru", "password": "password123"})
    first = client.post("/auth/login", json={"email": "r@sirius.ru", "password": "password123"}).json()

    second = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    replay = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})

    assert second.status_code == 200
    assert replay.status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": second.json()["refresh_token"]}).status_code == 401


def test_admin_sees_stats_refreshed_by_beat(client, storage):
    from datetime import UTC, datetime

    from app.modules.orders.repository import InMemoryOrderRepository
    from app.modules.orders.service import OrderStatsService

    student_id, student = create_account(client, storage, balance=1000)
    _, admin = create_account(client, storage, Role.ADMIN)
    item_id = client.post("/menu/items", json={"name": "Плов", "price": 150}, headers=admin).json()["item_id"]
    client.post("/orders/create", json={"item_id": item_id, "quantity": 2}, headers=student)
    OrderStatsService(InMemoryOrderRepository(storage)).refresh(datetime.now(UTC).date())

    response = client.get("/orders/stats", params={"days": 1}, headers=admin)

    assert response.status_code == 200
    [today] = response.json()
    assert (today["day"], today["orders"], today["revenue"]) == (datetime.now(UTC).date().isoformat(), 1, 300)
