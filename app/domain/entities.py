"""
Бизнес-сущности предметной области «Сириус.Еда» (круг 1 модели Мартина).
Не зависят ни от ORM, ни от веб-фреймворка.
"""
from dataclasses import dataclass


class OrderStatus:
    PROCESSING = "processing"
    PAID = "paid"
    DELIVERED = "delivered"


class DeliveryStatus:
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class User:
    id: int
    email: str
    phone: str | None
    balance: float
    is_blocked: bool


@dataclass
class MenuItem:
    id: int
    name: str
    price: float
    is_available: bool


@dataclass
class Order:
    id: int
    user_id: int
    item_id: int
    quantity: int
    status: str


@dataclass
class Delivery:
    id: int
    order_id: int
    courier_id: int | None
    status: str
