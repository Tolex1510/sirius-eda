"""
Определение ORM-моделей предметной области «Сириус.Еда».
"""
from datetime import UTC, datetime

from sqlalchemy import (
    JSON, BigInteger, Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, Numeric, PrimaryKeyConstraint, String, Text,
    UniqueConstraint, func, text,
)
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB
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
    balance = Column(Numeric(14, 2), default=0.0)
    is_blocked = Column(Boolean, default=False)
    password_hash = Column(String, nullable=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)

    role = relationship("Role", lazy="joined")

    def to_entity(self) -> entities.User:
        return entities.User(
            id=self.id,
            email=self.email,
            phone=self.phone,
            balance=float(self.balance),
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
    price = Column(Numeric(14, 2), nullable=False)
    is_available = Column(Boolean, default=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True, index=True)

    catalog_slug = Column(String(100), unique=True, nullable=True)
    description = Column(Text, nullable=False, default="", server_default="")
    ingredients = Column(JSON, nullable=False, default=list, server_default="[]")
    dietary_tags = Column(JSON, nullable=False, default=list, server_default="[]")
    portion_value = Column(Integer, nullable=True)
    portion_unit = Column(String(2), nullable=True)
    is_archived = Column(Boolean, nullable=False, default=False, server_default="false")

    def to_entity(self) -> entities.MenuItem:
        return entities.MenuItem(
            id=self.id,
            name=self.name,
            price=float(self.price),
            is_available=self.is_available,
            category_id=self.category_id,
            image_url=f"/menu-images/{self.catalog_slug}.webp" if self.catalog_slug else None,
            description=self.description or "",
            ingredients=self.ingredients or [],
            dietary_tags=self.dietary_tags or [],
            portion_value=self.portion_value,
            portion_unit=self.portion_unit,
            is_archived=bool(self.is_archived),
        )


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    item_id = Column(Integer, ForeignKey("menu_items.id"))
    quantity = Column(Integer, nullable=False)
    status = Column(String, default="processing")
    # Сумма фиксируется в момент заказа: цена блюда может измениться до отмены.
    total_cost = Column(Numeric(14, 2), nullable=False)
    payment_source = Column(String(20), nullable=False, default="internal_balance", server_default="internal_balance")
    correlation_id = Column(String(128), nullable=True)
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
            total_cost=float(self.total_cost),
            created_at=self.created_at,
            payment_source=self.payment_source,
            correlation_id=self.correlation_id,
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
    revenue = Column(Numeric(14, 2), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    def to_entity(self) -> entities.DailyOrderStats:
        return entities.DailyOrderStats(
            day=self.day, orders=self.orders, revenue=float(self.revenue), updated_at=self.updated_at
        )


class Delivery(Base):
    __tablename__ = "deliveries"
    # Доставку создают и сервис по событию OrderPaid, и курьер вручную: второй живой доставки на заказ быть не должно.
    __table_args__ = (
        Index(
            "uq_deliveries_order_id_active", "order_id", unique=True,
            postgresql_where=text("status <> 'cancelled'"), sqlite_where=text("status <> 'cancelled'"),
        ),
    )

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


class KitchenTicket(Base):
    """Заказ в очереди кухни. Один на заказ: повторное событие OrderPaid не создаст второй."""
    __tablename__ = "kitchen_tickets"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True)
    status = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    def to_entity(self) -> entities.KitchenTicket:
        return entities.KitchenTicket(id=self.id, order_id=self.order_id, status=self.status, created_at=self.created_at)


class OutboxEvent(Base):
    """
    Transactional Outbox: событие пишется в одной транзакции с изменением данных.
    В RabbitMQ его отправляет отдельный процесс, app/workers/outbox_relay.py.
    """
    __tablename__ = "outbox_events"
    __table_args__ = (
        # Релей ищет только неотправленные, а их единицы среди всей истории.
        Index(
            "ix_outbox_events_pending", "id",
            postgresql_where=text("published_at IS NULL"), sqlite_where=text("published_at IS NULL"),
        ),
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    event_id = Column(String(36), nullable=False, unique=True)
    routing_key = Column(String(100), nullable=False)
    payload = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    published_at = Column(DateTime(timezone=True), nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(String(500), nullable=True)


class ProcessedEvent(Base):
    """
    Inbox: какие события получатель уже обработал. Ключ включает получателя:
    одно событие OrderPaid обрабатывают и кухня, и доставка, а БД у них общая.
    """
    __tablename__ = "processed_events"
    __table_args__ = (PrimaryKeyConstraint("consumer", "event_id"),)

    consumer = Column(String(50), nullable=False)
    event_id = Column(String(36), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True)


class Payment(Base):
    """Одно платёжное намерение на заказ; повтор запроса не создаёт новый платёж."""
    __tablename__ = 'payments'
    __table_args__ = (UniqueConstraint('user_id', 'idempotency_key', name='uq_payments_user_key'),)
    id = Column(String(36), primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    provider = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default='creating')
    idempotency_key = Column(String(64), nullable=False)
    gateway_id = Column(String(100), unique=True, nullable=True)
    confirmation_url = Column(String(2048), nullable=True)
    refund_status = Column(String(20), nullable=True)
    refund_id = Column(String(100), nullable=True)
    refund_started_at = Column(DateTime(timezone=True), nullable=True)
    review_required = Column(Boolean, nullable=False, default=False, server_default="false")
    cancellation_reason = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class KnowledgeChunk(Base):
    __tablename__ = 'knowledge_chunks'
    id = Column(String(100), primary_key=True)
    content = Column(Text, nullable=False)
    url = Column(String(512), nullable=False)
    checksum = Column(String(64), nullable=False)
    embedding = Column(Vector(1024), nullable=False)
    embedding_model = Column(String(100), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class ChatConversation(Base):
    __tablename__ = 'chat_conversations'
    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class ChatMessage(Base):
    __tablename__ = 'chat_messages'
    id = Column(Integer, primary_key=True)
    conversation_id = Column(String(36), ForeignKey('chat_conversations.id'), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    sources = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
