"""
Бизнес-сущности предметной области «Сириус.Еда» (круг 1 модели Мартина).
Не зависят ни от ORM, ни от веб-фреймворка.
"""
from dataclasses import dataclass, field
from datetime import date, datetime


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
    # Курьер назначен и идёт на кухню.
    IN_PROGRESS = "in_progress"
    # Курьер забрал заказ и везёт его.
    ON_THE_WAY = "on_the_way"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    ACTIVE = (IN_PROGRESS, ON_THE_WAY)
    FINAL = (COMPLETED, CANCELLED)


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
    category_id: int | None = None
    image_url: str | None = None
    description: str = ""
    ingredients: list[str] = field(default_factory=list)
    dietary_tags: list[str] = field(default_factory=list)
    portion_value: int | None = None
    portion_unit: str | None = None
    is_archived: bool = False


@dataclass
class Category:
    id: int
    name: str


@dataclass
class CategoryMenu:
    """Категория вместе с её блюдами: так её отдаёт GET /menu/categories/{id}."""
    id: int
    name: str
    items: list[MenuItem]


@dataclass
class Order:
    id: int
    user_id: int
    item_id: int
    quantity: int
    status: str
    total_cost: float = 0.0
    created_at: datetime | None = None
    payment_source: str = "internal_balance"
    correlation_id: str | None = None


@dataclass
class DailyOrderStats:
    """Сводка заказов за сутки по UTC. Отменённые заказы не учитываются."""
    day: date
    orders: int
    revenue: float
    updated_at: datetime


@dataclass
class Delivery:
    id: int
    order_id: int
    courier_id: int | None
    status: str


class KitchenTicketStatus:
    QUEUED = "queued"
    CANCELLED = "cancelled"


@dataclass
class KitchenTicket:
    """Заказ в очереди кухни. Появляется по событию OrderPaid."""
    id: int
    order_id: int
    status: str
    created_at: datetime | None = None


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


@dataclass
class ExternalIdentity:
    """Пользователь, подтверждённый внешним провайдером."""
    provider: str
    subject: str
    email: str | None
    email_verified: bool
