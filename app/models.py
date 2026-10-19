"""
Определение ORM-моделей предметной области «Сириус.Еда».
"""
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship
from app.database import Base
from app.domain import entities


class Role(Base):
    """Роль пользователя: student, cook, courier, admin."""
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False)
    phone = Column(String, nullable=True)
    balance = Column(Float, default=0.0)
    is_blocked = Column(Boolean, default=False)
    password_hash = Column(String, nullable=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)

    role = relationship("Role", lazy="joined")

    def to_entity(self) -> entities.User:
        return entities.User(
            id=self.id,
            email=self.email,
            phone=self.phone,
            balance=self.balance,
            is_blocked=self.is_blocked,
            role=self.role.name,
            password_hash=self.password_hash,
        )


class Category(Base):
    """Раздел меню: супы, горячее, напитки."""
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)

    def to_entity(self) -> entities.Category:
        return entities.Category(id=self.id, name=self.name)


class MenuItem(Base):
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    is_available = Column(Boolean, default=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True, index=True)

    def to_entity(self) -> entities.MenuItem:
        return entities.MenuItem(
            id=self.id,
            name=self.name,
            price=self.price,
            is_available=self.is_available,
            category_id=self.category_id,
        )


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    item_id = Column(Integer, ForeignKey("menu_items.id"))
    quantity = Column(Integer, nullable=False)
    status = Column(String, default="processing")
    # Сумма фиксируется в момент заказа: цена блюда может измениться до отмены.
    total_cost = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), server_default=func.now())

    user = relationship("User")
    item = relationship("MenuItem")

    def to_entity(self) -> entities.Order:
        return entities.Order(
            id=self.id,
            user_id=self.user_id,
            item_id=self.item_id,
            quantity=self.quantity,
            status=self.status,
            total_cost=self.total_cost,
            created_at=self.created_at,
        )


class TaskLog(Base):
    """
    Журнал фоновых задач заказа. Пара (order_id, kind) уникальна:
    по ней задача узнаёт, что уже выполнена, и не шлёт второй чек или письмо.
    """
    __tablename__ = "task_logs"
    __table_args__ = (UniqueConstraint("order_id", "kind", name="uq_task_logs_order_id_kind"),)

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False)
    attempts = Column(Integer, nullable=False, default=1)
    error = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class OrderStats(Base):
    """Сводка заказов за день. Пересчитывает периодическая задача Celery Beat."""
    __tablename__ = "order_stats"

    day = Column(Date, primary_key=True)
    orders = Column(Integer, nullable=False)
    revenue = Column(Float, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    def to_entity(self) -> entities.DailyOrderStats:
        return entities.DailyOrderStats(
            day=self.day, orders=self.orders, revenue=self.revenue, updated_at=self.updated_at
        )


class Delivery(Base):
    __tablename__ = "deliveries"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    courier_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(String, default="pending")

    order = relationship("Order")
    courier = relationship("User")

    def to_entity(self) -> entities.Delivery:
        return entities.Delivery(
            id=self.id,
            order_id=self.order_id,
            courier_id=self.courier_id,
            status=self.status,
        )


class RefreshToken(Base):
    """Выданный refresh-токен. Хранится хеш, чтобы утечка БД не дала рабочих токенов."""
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_revoked = Column(Boolean, nullable=False, default=False, server_default="false")


class ExternalAccount(Base):
    """Привязка аккаунта внешнего провайдера (Google) к пользователю."""
    __tablename__ = "external_accounts"
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_external_accounts_provider_subject"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(32), nullable=False)
    # Постоянный id пользователя у провайдера (claim sub). Email может смениться, sub нет.
    subject = Column(String(255), nullable=False)
    email = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
