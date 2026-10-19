"""
Тесты безопасности из задания: без токена 401, чужая роль 403,
чужой объект 403, rate limiting 429. Плюс Secure by Default.
"""
import importlib

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.rate_limit import get_redis
from app.core.redis import create_redis
from app.domain.entities import DeliveryStatus, OrderStatus, Role
from tests.conftest import add_delivery, add_menu_item, add_order, create_account

PROTECTED = [
    ("post", "/orders/create", {"item_id": 1, "quantity": 1}),
    ("get", "/orders/my", None),
    ("post", "/orders/1/cancel", None),
    ("get", "/kitchen/orders", None),
    ("get", "/orders/stats", None),
    ("get", "/users/me", None),
    ("get", "/users/1", None),
    ("post", "/users/1/topup?amount=10", None),
    ("patch", "/users/1/role", {"role": "admin"}),
    ("post", "/menu/items", {"name": "Борщ", "price": 100}),
    ("patch", "/menu/items/1", {"price": 1}),
    ("post", "/delivery/assign", {"order_id": 1, "courier_id": 1}),
    ("get", "/delivery/my", None),
    ("get", "/delivery/1", None),
    ("patch", "/delivery/1/complete", None),
]


@pytest.mark.parametrize(("method", "url", "body"), PROTECTED, ids=[f"{m} {u}" for m, u, _ in PROTECTED])
def test_no_token_gives_401(client, method, url, body):
    response = client.request(method, url, json=body)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("token", ["garbage", "a.b.c", ""])
def test_malformed_token_gives_401(client, token):
    response = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_refresh_token_as_bearer_gives_401(client, storage):
    client.post("/users/register", json={"email": "r@sirius.ru", "password": "password123"})
    refresh = client.post("/auth/login", json={"email": "r@sirius.ru", "password": "password123"}).json()["refresh_token"]

    assert client.get("/users/me", headers={"Authorization": f"Bearer {refresh}"}).status_code == 401


WRONG_ROLE = [
    (Role.STUDENT, "get", "/kitchen/orders", None),
    (Role.COURIER, "get", "/kitchen/orders", None),
    (Role.STUDENT, "get", "/orders/stats", None),
    (Role.COOK, "get", "/orders/stats", None),
    (Role.STUDENT, "post", "/menu/items", {"name": "Борщ", "price": 100}),
    (Role.COURIER, "patch", "/menu/items/1", {"price": 1}),
    (Role.COOK, "post", "/orders/create", {"item_id": 1, "quantity": 1}),
    (Role.COURIER, "post", "/orders/create", {"item_id": 1, "quantity": 1}),
    (Role.STUDENT, "post", "/delivery/assign", {"order_id": 1, "courier_id": 1}),
    (Role.STUDENT, "patch", "/delivery/1/complete", None),
    (Role.COOK, "patch", "/users/1/role", {"role": "admin"}),
    (Role.STUDENT, "patch", "/users/1/role", {"role": "admin"}),
]


@pytest.mark.parametrize(("role", "method", "url", "body"), WRONG_ROLE, ids=[f"{r} {m} {u}" for r, m, u, _ in WRONG_ROLE])
def test_wrong_role_gives_403(client, storage, role, method, url, body):
    _, headers = create_account(client, storage, role)

    response = client.request(method, url, json=body, headers=headers)

    assert response.status_code == 403
    assert response.json() == {"detail": "Недостаточно прав для этого действия"}


def test_student_cannot_promote_self(client, storage):
    student_id, student = create_account(client, storage)

    client.patch(f"/users/{student_id}/role", json={"role": "admin"}, headers=student)

    assert storage.users[student_id].role == Role.STUDENT


def test_foreign_order_cancel_gives_403(client, storage):
    victim_id, victim = create_account(client, storage, balance=500)
    _, attacker = create_account(client, storage)
    order = add_order(storage, victim_id, add_menu_item(storage).id, OrderStatus.PROCESSING)

    response = client.post(f"/orders/{order.id}/cancel", headers=attacker)

    assert response.status_code == 403
    assert storage.orders[order.id].status == OrderStatus.PROCESSING


def test_foreign_account_gives_403(client, storage):
    victim_id, _ = create_account(client, storage, balance=100)
    _, attacker = create_account(client, storage)

    assert client.get(f"/users/{victim_id}", headers=attacker).status_code == 403
    assert client.post(f"/users/{victim_id}/topup", params={"amount": 10}, headers=attacker).status_code == 403
    assert storage.users[victim_id].balance == 100


def test_foreign_delivery_gives_403(client, storage):
    customer_id, _ = create_account(client, storage)
    courier_id, _ = create_account(client, storage, Role.COURIER)
    _, other_student = create_account(client, storage)
    _, other_courier = create_account(client, storage, Role.COURIER)
    order = add_order(storage, customer_id, add_menu_item(storage).id, OrderStatus.PAID)
    delivery = add_delivery(storage, order.id, courier_id, DeliveryStatus.IN_PROGRESS)

    assert client.get(f"/delivery/{delivery.id}", headers=other_student).status_code == 403
    assert client.get(f"/delivery/{delivery.id}", headers=other_courier).status_code == 403
    assert client.patch(f"/delivery/{delivery.id}/complete", headers=other_courier).status_code == 403
    assert client.get("/delivery/my", headers=other_courier).json() == []
    assert storage.deliveries[delivery.id].status == DeliveryStatus.IN_PROGRESS


def test_courier_cannot_assign_other_courier(client, storage):
    customer_id, _ = create_account(client, storage)
    victim_id, _ = create_account(client, storage, Role.COURIER)
    _, courier = create_account(client, storage, Role.COURIER)
    order = add_order(storage, customer_id, add_menu_item(storage).id, OrderStatus.PAID)

    response = client.post("/delivery/assign", json={"order_id": order.id, "courier_id": victim_id}, headers=courier)

    assert response.status_code == 403


def test_login_bruteforce_gives_429(client, storage):
    client.post("/users/register", json={"email": "victim@sirius.ru", "password": "password123"})
    wrong = {"email": "victim@sirius.ru", "password": "wrong-password"}

    codes = [client.post("/auth/login", json=wrong).status_code for _ in range(6)]

    assert codes == [401] * 5 + [429]
    assert int(client.post("/auth/login", json=wrong).headers["Retry-After"]) > 0


def test_login_and_token_share_one_limit(client):
    for _ in range(3):
        client.post("/auth/login", json={"email": "a@sirius.ru", "password": "x"})
    for _ in range(2):
        client.post("/auth/token", data={"username": "a@sirius.ru", "password": "x"})

    assert client.post("/auth/token", data={"username": "a@sirius.ru", "password": "x"}).status_code == 429


def test_registration_spam_gives_429(client):
    codes = [
        client.post("/users/register", json={"email": f"spam{i}@sirius.ru", "password": "password123"}).status_code
        for i in range(6)
    ]

    assert codes == [200] * 5 + [429]


def test_redis_outage_does_not_block_login(client, storage):
    from app.main import app

    app.dependency_overrides[get_redis] = lambda: create_redis("redis://127.0.0.1:1/0")
    client.post("/users/register", json={"email": "ok@sirius.ru", "password": "password123"})

    response = client.post("/auth/login", json={"email": "ok@sirius.ru", "password": "password123"})

    assert response.status_code == 200


def test_password_is_not_stored_in_plain_text(client, storage):
    user_id = client.post("/users/register", json={"email": "p@sirius.ru", "password": "password123"}).json()["user_id"]

    assert "password123" not in storage.users[user_id].password_hash


def test_password_is_not_returned(client, storage):
    _, headers = create_account(client, storage)

    assert "password_hash" not in client.get("/users/me", headers=headers).json()


def test_cors_allows_only_configured_origins(client):
    preflight = {"Access-Control-Request-Method": "POST"}

    evil = client.options("/auth/login", headers={"Origin": "https://evil.example", **preflight})

    assert "access-control-allow-origin" not in evil.headers


@pytest.fixture
def production_app(monkeypatch):
    import app.main

    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "ALLOWED_ORIGINS", ["https://sirius-food.ru"])
    yield importlib.reload(app.main).app
    monkeypatch.undo()
    importlib.reload(app.main)


def test_swagger_is_disabled_in_production(production_app):
    client = TestClient(production_app)

    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_cors_allows_own_domain_in_production(production_app):
    client = TestClient(production_app)

    response = client.options(
        "/auth/login",
        headers={"Origin": "https://sirius-food.ru", "Access-Control-Request-Method": "POST"},
    )

    assert response.headers["access-control-allow-origin"] == "https://sirius-food.ru"


def test_secret_key_is_required(monkeypatch):
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.delenv("SECRET_KEY")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_short_secret_key_is_rejected(monkeypatch):
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.setenv("SECRET_KEY", "short")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
