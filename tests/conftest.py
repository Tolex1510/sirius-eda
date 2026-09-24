import os

# Приложение импортируется без СУБД: таблицы PostgreSQL не создаются.
os.environ.setdefault("REPOSITORY_BACKEND", "memory")

import pytest

from app.domain.entities import Delivery, MenuItem, Order, User
from app.memory_storage import InMemoryStorage


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


def add_user(storage: InMemoryStorage, balance: float = 0.0, is_blocked: bool = False) -> User:
    user_id = storage.next_id("users")
    user = User(id=user_id, email=f"user{user_id}@sirius.ru", phone=None, balance=balance, is_blocked=is_blocked)
    storage.users[user_id] = user
    return user


def add_menu_item(storage: InMemoryStorage, price: float = 100.0, is_available: bool = True) -> MenuItem:
    item_id = storage.next_id("menu_items")
    item = MenuItem(id=item_id, name=f"Блюдо {item_id}", price=price, is_available=is_available)
    storage.menu_items[item_id] = item
    return item


def add_order(storage: InMemoryStorage, user_id: int, item_id: int, status: str) -> Order:
    order_id = storage.next_id("orders")
    order = Order(id=order_id, user_id=user_id, item_id=item_id, quantity=1, status=status)
    storage.orders[order_id] = order
    return order


def add_delivery(storage: InMemoryStorage, order_id: int, courier_id: int, status: str) -> Delivery:
    delivery_id = storage.next_id("deliveries")
    delivery = Delivery(id=delivery_id, order_id=order_id, courier_id=courier_id, status=status)
    storage.deliveries[delivery_id] = delivery
    return delivery
