"""
Event-driven часть без брокера: оплата с outbox, consumer'ы кухни, доставки и заказов,
идемпотентность и сага. Репозитории проверяются и в памяти, и на SQLite.
"""
import asyncio
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.domain.entities import DeliveryStatus, KitchenTicketStatus, OrderStatus, Role
from app.domain.events import (
    DeliveryFailed, InvalidEventError, OrderCancelled, OrderPaid, Receipt, parse_event,
)
from app.domain.exceptions import AccessDeniedError, AlreadyProcessedError, BusinessRuleError
from app.memory_storage import InMemoryStorage
from app.models import KitchenTicket as KitchenTicketModel
from app.models import MenuItem as MenuItemModel
from app.models import Order as OrderModel
from app.models import OutboxEvent, ProcessedEvent
from app.models import Role as RoleModel
from app.models import User as UserModel
from app.modules.delivery.repository import InMemoryDeliveryRepository, SqlAlchemyDeliveryRepository
from app.modules.delivery.service import DeliveryService
from app.modules.kitchen.repository import InMemoryKitchenRepository, SqlAlchemyKitchenRepository
from app.modules.kitchen.service import KitchenService
from app.modules.orders.repository import InMemoryOrderRepository, SqlAlchemyOrderRepository
from app.modules.orders.service import OrderService
from app.workers.consumer import EventConsumer
from app.core.rabbitmq import KITCHEN
from tests.conftest import RecordingNotifier, add_delivery, add_menu_item, add_order, add_user, create_account


# События

def test_event_survives_json_round_trip():
    event = OrderPaid(order_id=7, customer_id=3, amount=250.0)
    parsed = parse_event(json.loads(json.dumps(event.to_payload())))
    assert parsed == event


@pytest.mark.parametrize("payload", [
    "not an object",
    {"event_type": "order.unknown"},
    {"event_type": "order.paid", "event_id": "x", "occurred_at": "2026-10-24T10:00:00+00:00", "customer_id": 1, "amount": 1},
    {"event_type": "order.paid", "event_id": "x", "occurred_at": "2026-10-24T10:00:00+00:00",
     "order_id": "7", "customer_id": 1, "amount": 1},
    {"event_type": "order.paid", "event_id": "x", "occurred_at": "2026-10-24T10:00:00+00:00",
     "order_id": True, "customer_id": 1, "amount": 1},
    {"event_type": "order.paid", "event_id": "", "occurred_at": "2026-10-24T10:00:00+00:00",
     "order_id": 7, "customer_id": 1, "amount": 1},
    {"event_type": "order.paid", "event_id": "x", "occurred_at": "2026-10-24T10:00:00",
     "order_id": 7, "customer_id": 1, "amount": 1},
], ids=["not-object", "unknown-type", "missing-field", "string-id", "bool-id", "empty-event-id", "naive-date"])
def test_invalid_payload_is_rejected(payload):
    with pytest.raises(InvalidEventError):
        parse_event(payload)


# Репозитории в памяти и на SQLite

class Sql:
    """Те же сценарии на SQL-репозиториях. SQLite в памяти, PostgreSQL не нужен."""

    def __init__(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.db.add_all(RoleModel(name=name) for name in Role.ALL)
        self.db.commit()
        self.roles = {r.name: r.id for r in self.db.query(RoleModel)}

    def user(self, role=Role.STUDENT, balance=0.0, is_blocked=False) -> int:
        row = UserModel(email=f"{role}{self.db.query(UserModel).count()}@sirius.ru", balance=balance,
                        is_blocked=is_blocked, role_id=self.roles[role])
        self.db.add(row)
        self.db.commit()
        return row.id

    def order(self, user_id, status, total_cost=100.0) -> int:
        item = MenuItemModel(name=f"Блюдо {user_id}", price=total_cost)
        self.db.add(item)
        self.db.flush()
        row = OrderModel(user_id=user_id, item_id=item.id, quantity=1, status=status, total_cost=total_cost)
        self.db.add(row)
        self.db.commit()
        return row.id

    def delivery(self, order_id, courier_id, status):
        SqlAlchemyDeliveryRepository(self.db).create(order_id, courier_id, status)

    def order_status(self, order_id):
        self.db.expire_all()
        return self.db.get(OrderModel, order_id).status

    def balance(self, user_id):
        self.db.expire_all()
        return self.db.get(UserModel, user_id).balance

    def outbox(self) -> list[tuple[str, dict]]:
        return [(r.routing_key, r.payload) for r in self.db.query(OutboxEvent).order_by(OutboxEvent.id)]

    def receipts(self) -> set[tuple[str, str]]:
        return {(r.consumer, r.event_id) for r in self.db.query(ProcessedEvent)}

    def tickets(self) -> list[tuple[int, str]]:
        self.db.expire_all()
        return [(t.order_id, t.status) for t in self.db.query(KitchenTicketModel).order_by(KitchenTicketModel.id)]

    def orders_repo(self): return SqlAlchemyOrderRepository(self.db)
    def kitchen_repo(self): return SqlAlchemyKitchenRepository(self.db)
    def delivery_repo(self): return SqlAlchemyDeliveryRepository(self.db)


class Memory:
    def __init__(self):
        self.storage = InMemoryStorage()

    def user(self, role=Role.STUDENT, balance=0.0, is_blocked=False) -> int:
        return add_user(self.storage, balance=balance, role=role, is_blocked=is_blocked).id

    def order(self, user_id, status, total_cost=100.0) -> int:
        item = add_menu_item(self.storage, price=total_cost)
        return add_order(self.storage, user_id, item.id, status, total_cost).id

    def delivery(self, order_id, courier_id, status):
        add_delivery(self.storage, order_id, courier_id, status)

    def order_status(self, order_id):
        return self.storage.orders[order_id].status

    def balance(self, user_id):
        return self.storage.users[user_id].balance

    def outbox(self):
        return [(e.ROUTING_KEY, e.to_payload()) for e in self.storage.outbox]

    def receipts(self):
        return {(r.consumer, r.event_id) for r in self.storage.receipts}

    def tickets(self):
        return [(t.order_id, t.status) for t in self.storage.kitchen_tickets.values()]

    def orders_repo(self): return InMemoryOrderRepository(self.storage)
    def kitchen_repo(self): return InMemoryKitchenRepository(self.storage)
    def delivery_repo(self): return InMemoryDeliveryRepository(self.storage)


@pytest.fixture(params=[Memory, Sql], ids=["memory", "sqlite"])
def world(request):
    return request.param()


def orders(world) -> OrderService:
    return OrderService(world.orders_repo(), RecordingNotifier())


# Оплата: статус и событие одной транзакцией

def test_pay_order_writes_event_to_outbox(world):
    student = world.user(balance=0)
    order_id = world.order(student, OrderStatus.PROCESSING, total_cost=250.0)
    actor = world.orders_repo().get_user_by_id(student)

    order = orders(world).pay_order(order_id, actor)

    assert order.status == world.order_status(order_id) == OrderStatus.PAID
    [(routing_key, payload)] = world.outbox()
    assert routing_key == "order.paid"
    assert payload["order_id"] == order_id and payload["customer_id"] == student and payload["amount"] == 250.0


def test_second_payment_is_refused_and_publishes_nothing(world):
    student = world.user()
    order_id = world.order(student, OrderStatus.PROCESSING)
    actor = world.orders_repo().get_user_by_id(student)
    orders(world).pay_order(order_id, actor)

    with pytest.raises(BusinessRuleError):
        orders(world).pay_order(order_id, actor)
    assert len(world.outbox()) == 1


def test_cannot_pay_foreign_order(world):
    owner, stranger = world.user(), world.user()
    order_id = world.order(owner, OrderStatus.PROCESSING)

    with pytest.raises(AccessDeniedError):
        orders(world).pay_order(order_id, world.orders_repo().get_user_by_id(stranger))
    assert world.order_status(order_id) == OrderStatus.PROCESSING
    assert world.outbox() == []


def test_pay_endpoint(client, storage):
    student_id, headers = create_account(client, storage, balance=500)
    item = add_menu_item(storage, price=120)
    order_id = client.post("/orders/create", headers=headers, json={"item_id": item.id, "quantity": 1}).json()["order_id"]

    response = client.post(f"/orders/{order_id}/pay", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"status": "success", "order_id": order_id, "order_status": "paid"}
    assert [e.order_id for e in storage.outbox] == [order_id]
    assert client.post(f"/orders/{order_id}/pay", headers=headers).status_code == 400


# Кухня

def test_kitchen_queues_paid_order_once(world):
    order_id = world.order(world.user(), OrderStatus.PAID)
    event = OrderPaid(order_id=order_id, customer_id=1, amount=100.0)
    kitchen = KitchenService(world.kitchen_repo())

    ticket = kitchen.accept(event, Receipt("kitchen", event.event_id))
    with pytest.raises(AlreadyProcessedError):
        kitchen.accept(event, Receipt("kitchen", event.event_id))

    assert ticket.order_id == order_id
    assert world.tickets() == [(order_id, KitchenTicketStatus.QUEUED)]
    assert [t.order_id for t in kitchen.queue()] == [order_id]


def test_kitchen_removes_cancelled_order(world):
    order_id = world.order(world.user(), OrderStatus.PAID)
    kitchen = KitchenService(world.kitchen_repo())
    paid = OrderPaid(order_id=order_id, customer_id=1, amount=100.0)
    kitchen.accept(paid, Receipt("kitchen", paid.event_id))

    cancelled = OrderCancelled(order_id=order_id, customer_id=1, refund=100.0, reason="Нет свободного курьера")
    assert kitchen.cancel(cancelled, Receipt("kitchen", cancelled.event_id)) is True

    assert world.tickets() == [(order_id, KitchenTicketStatus.CANCELLED)]
    assert kitchen.queue() == []


def test_late_payment_does_not_queue_cancelled_order(world):
    """Отмена пришла раньше оплаты: например, сообщение об оплате вернулось из DLQ."""
    order_id = world.order(world.user(), OrderStatus.CANCELLED)
    kitchen = KitchenService(world.kitchen_repo())
    cancelled = OrderCancelled(order_id=order_id, customer_id=1, refund=100.0, reason="тест")
    paid = OrderPaid(order_id=order_id, customer_id=1, amount=100.0)

    kitchen.cancel(cancelled, Receipt("kitchen", cancelled.event_id))
    assert kitchen.accept(paid, Receipt("kitchen", paid.event_id)) is None
    assert world.tickets() == [(order_id, KitchenTicketStatus.CANCELLED)]


def test_receipts_are_per_consumer(world):
    """Одно событие обрабатывают и кухня, и доставка: отметка кухни не должна остановить доставку."""
    world.user(role=Role.COURIER)
    order_id = world.order(world.user(), OrderStatus.PAID)
    event = OrderPaid(order_id=order_id, customer_id=1, amount=100.0)

    KitchenService(world.kitchen_repo()).accept(event, Receipt("kitchen", event.event_id))
    delivery = DeliveryService(world.delivery_repo()).dispatch(event, Receipt("delivery", event.event_id))

    assert delivery.status == DeliveryStatus.IN_PROGRESS
    assert world.receipts() == {("kitchen", event.event_id), ("delivery", event.event_id)}


# Доставка

def test_dispatch_assigns_first_free_courier(world):
    busy = world.user(role=Role.COURIER)
    world.user(role=Role.COURIER, is_blocked=True)
    free = world.user(role=Role.COURIER)
    world.delivery(world.order(world.user(), OrderStatus.PAID), busy, DeliveryStatus.ON_THE_WAY)
    order_id = world.order(world.user(), OrderStatus.PAID)
    event = OrderPaid(order_id=order_id, customer_id=1, amount=100.0)

    delivery = DeliveryService(world.delivery_repo()).dispatch(event, Receipt("delivery", event.event_id))

    assert (delivery.order_id, delivery.courier_id, delivery.status) == (order_id, free, DeliveryStatus.IN_PROGRESS)
    assert world.outbox() == []


def test_dispatch_without_couriers_publishes_delivery_failed(world):
    order_id = world.order(world.user(), OrderStatus.PAID)
    event = OrderPaid(order_id=order_id, customer_id=1, amount=100.0)
    service = DeliveryService(world.delivery_repo())

    result = service.dispatch(event, Receipt("delivery", event.event_id))
    with pytest.raises(AlreadyProcessedError):
        service.dispatch(event, Receipt("delivery", event.event_id))

    assert isinstance(result, DeliveryFailed)
    [(routing_key, payload)] = world.outbox()
    assert routing_key == "delivery.failed" and payload["order_id"] == order_id


def test_dispatch_skips_cancelled_order(world):
    world.user(role=Role.COURIER)
    order_id = world.order(world.user(), OrderStatus.CANCELLED)
    event = OrderPaid(order_id=order_id, customer_id=1, amount=100.0)

    assert DeliveryService(world.delivery_repo()).dispatch(event, Receipt("delivery", event.event_id)) is None
    assert world.outbox() == []


def test_manual_assign_refuses_second_delivery(world):
    first, second = world.user(role=Role.COURIER), world.user(role=Role.COURIER)
    order_id = world.order(world.user(), OrderStatus.PAID)
    world.delivery(order_id, first, DeliveryStatus.IN_PROGRESS)
    admin = world.delivery_repo().get_courier_by_id(world.user(role=Role.ADMIN))

    with pytest.raises(BusinessRuleError, match="уже есть доставка"):
        DeliveryService(world.delivery_repo()).assign_courier(order_id, second, admin)


# Сага: компенсация

def test_compensation_refunds_once_and_publishes_order_cancelled(world):
    student = world.user(balance=50.0)
    order_id = world.order(student, OrderStatus.PAID, total_cost=200.0)
    failed = DeliveryFailed(order_id=order_id, reason="Нет свободного курьера")
    receipt = Receipt("orders", failed.event_id)

    cancelled = orders(world).compensate_failed_delivery(failed, receipt)
    with pytest.raises(AlreadyProcessedError):
        orders(world).compensate_failed_delivery(failed, receipt)

    assert world.order_status(order_id) == OrderStatus.CANCELLED
    assert world.balance(student) == 250.0
    assert cancelled.refund == 200.0 and cancelled.reason == "Нет свободного курьера"
    [(routing_key, payload)] = world.outbox()
    assert routing_key == "order.cancelled" and payload["order_id"] == order_id


def test_compensation_ignores_order_that_is_not_paid(world):
    student = world.user(balance=0.0)
    order_id = world.order(student, OrderStatus.DELIVERED)
    failed = DeliveryFailed(order_id=order_id, reason="тест")

    assert orders(world).compensate_failed_delivery(failed, Receipt("orders", failed.event_id)) is None
    assert world.order_status(order_id) == OrderStatus.DELIVERED
    assert world.balance(student) == 0.0


def test_saga_end_to_end_in_memory():
    """Outbox играет роль брокера: каждое событие доставляется всем подписчикам по очереди."""
    world = Memory()
    student = world.user(balance=0.0)
    order_id = world.order(student, OrderStatus.PROCESSING, total_cost=300.0)
    subscribers = {
        "order.paid": [
            ("kitchen", lambda e, r: KitchenService(world.kitchen_repo()).accept(e, r)),
            ("delivery", lambda e, r: DeliveryService(world.delivery_repo()).dispatch(e, r)),
        ],
        "delivery.failed": [("orders", lambda e, r: orders(world).compensate_failed_delivery(e, r))],
        "order.cancelled": [("kitchen", lambda e, r: KitchenService(world.kitchen_repo()).cancel(e, r))],
    }

    orders(world).pay_order(order_id, world.orders_repo().get_user_by_id(student))
    delivered = 0
    while delivered < len(world.storage.outbox):
        event = world.storage.outbox[delivered]
        delivered += 1
        for consumer, handle in subscribers[event.ROUTING_KEY]:
            handle(event, Receipt(consumer, event.event_id))

    assert [e.ROUTING_KEY for e in world.storage.outbox] == ["order.paid", "delivery.failed", "order.cancelled"]
    assert world.order_status(order_id) == OrderStatus.CANCELLED
    assert world.balance(student) == 300.0
    assert world.tickets() == [(order_id, KitchenTicketStatus.CANCELLED)]


# Цикл consumer'а без брокера

class FakeMessage:
    def __init__(self, body: bytes, delivery_count: int | None = None):
        self.body = body
        self.message_id = "m1"
        self.headers = {"x-delivery-count": delivery_count} if delivery_count is not None else {}
        self.result = None

    async def ack(self):
        self.result = "ack"

    async def nack(self, requeue=True):
        self.result = f"nack requeue={requeue}"

    async def reject(self, requeue=False):
        self.result = f"reject requeue={requeue}"


def run_consumer(handler, message: FakeMessage, monkeypatch):
    monkeypatch.setattr("app.workers.consumer.RETRY_DELAY_SECONDS", 0)
    asyncio.run(EventConsumer("kitchen", KITCHEN, {OrderPaid: handler}).handle(message))
    return message.result


def paid_message(**kwargs) -> FakeMessage:
    event = OrderPaid(order_id=1, customer_id=2, amount=10.0)
    return FakeMessage(json.dumps(event.to_payload()).encode(), **kwargs)


def test_consumer_acks_processed_event(monkeypatch):
    seen = []
    assert run_consumer(lambda e, r: seen.append(r) or "ok", paid_message(), monkeypatch) == "ack"
    assert seen[0].consumer == "kitchen"


def test_consumer_acks_duplicate(monkeypatch):
    def duplicate(event, receipt):
        raise AlreadyProcessedError("уже")
    assert run_consumer(duplicate, paid_message(), monkeypatch) == "ack"


@pytest.mark.parametrize("body", [b"not-json", b'{"event_type": "order.paid"}', b"\xff\xfe"])
def test_consumer_sends_broken_message_straight_to_dlq(body, monkeypatch):
    assert run_consumer(lambda e, r: "ok", FakeMessage(body), monkeypatch) == "reject requeue=False"


def test_consumer_returns_failed_message_to_queue(monkeypatch):
    def broken(event, receipt):
        raise RuntimeError("БД недоступна")
    # Решение о DLQ принимает очередь по счётчику доставок, consumer только возвращает сообщение.
    assert run_consumer(broken, paid_message(), monkeypatch) == "nack requeue=True"
    assert run_consumer(broken, paid_message(delivery_count=3), monkeypatch) == "nack requeue=True"


# Релей outbox без брокера

class FakeStore:
    def __init__(self, events):
        from app.outbox import PendingEvent
        self.events = [
            PendingEvent(i, e.event_id, e.ROUTING_KEY, e.to_payload(), e.occurred_at) for i, e in enumerate(events, 1)
        ]
        self.published, self.failures = [], []

    def fetch_pending(self, limit):
        return [e for e in self.events if e.id not in self.published][:limit]

    def mark_published(self, ids):
        self.published += ids

    def record_failure(self, outbox_id, error):
        self.failures.append(outbox_id)

    def pending(self):
        return len(self.events) - len(self.published), None


class FakeExchange:
    def __init__(self, fail_on: int | None = None):
        self.sent, self.fail_on = [], fail_on

    async def publish(self, message, routing_key, timeout=None):
        if len(self.sent) + 1 == self.fail_on:
            raise ConnectionError("broker gone")
        self.sent.append((routing_key, json.loads(message.body)["order_id"], message.message_id))


def test_relay_publishes_in_order_and_marks_events():
    from app.workers.outbox_relay import OutboxRelay

    events = [OrderPaid(order_id=n, customer_id=1, amount=1.0) for n in (1, 2, 3)]
    store, exchange = FakeStore(events), FakeExchange()

    assert asyncio.run(OutboxRelay(store).publish_pending(exchange)) == 3
    assert [order_id for _, order_id, _ in exchange.sent] == [1, 2, 3]
    assert [message_id for _, _, message_id in exchange.sent] == [e.event_id for e in events]
    assert store.published == [1, 2, 3]


def test_relay_stops_on_broker_error_and_keeps_the_rest():
    from app.workers.outbox_relay import OutboxRelay

    store = FakeStore([OrderPaid(order_id=n, customer_id=1, amount=1.0) for n in (1, 2, 3)])

    with pytest.raises(ConnectionError):
        asyncio.run(OutboxRelay(store).publish_pending(FakeExchange(fail_on=2)))

    assert store.published == [1]
    assert store.failures == [2]
    assert [e.id for e in store.fetch_pending(10)] == [2, 3]
