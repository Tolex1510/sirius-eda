"""
Бизнес-сущности предметной области «Сириус.Еда» (круг 1 модели Мартина).
Не зависят ни от ORM, ни от веб-фреймворка.
"""
from dataclasses import dataclass
from datetime import datetime


class Role:
    STUDENT = "student"
    COOK = "cook"
    COURIER = "courier"
    ADMIN = "admin"

    ALL = (STUDENT, COOK, COURIER, ADMIN)


class OrderStatus:
    PROCESSING = "processing"
    PAID = "paid"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


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
    role: str = Role.STUDENT
    # None у пользователей, вошедших только через внешнего провайдера.
    password_hash: str | None = None


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
    total_cost: float = 0.0


@dataclass
class Delivery:
    id: int
    order_id: int
    courier_id: int | None
    status: str


@dataclass
class RefreshTokenRecord:
    id: int
    user_id: int
    token_hash: str
    expires_at: datetime
    is_revoked: bool


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
