"""
Интеграционные тесты consumer'ов на настоящем RabbitMQ: docker compose up -d rabbitmq.
Без брокера тесты пропускаются. Каждый тест работает в своих очередях с уникальным префиксом
и удаляет их, рабочие очереди не затрагиваются. Хранилище в памяти, PostgreSQL не нужен.
"""
import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager

import aio_pika
import pytest

from app import dependencies
from app.core.rabbitmq import DELIVERY, DELIVERY_LIMIT, KITCHEN, ORDERS, Topology, event_message
from app.domain.entities import KitchenTicketStatus, OrderStatus, Role
from app.domain.events import OrderPaid, Receipt
from app.memory_storage import InMemoryStorage
from app.modules.delivery.repository import InMemoryDeliveryRepository
from app.modules.delivery.service import DeliveryService
from app.outbox import PendingEvent
from app.workers import consumer as consumer_module
from app.workers import kitchen_consumer, orders_consumer
from app.workers.consumer import EventConsumer
from app.workers.dead_letters import replay_dead_letters
from app.workers.outbox_relay import OutboxRelay
from tests.conftest import add_menu_item, add_order, add_user

URL = os.environ.get("RABBITMQ_TEST_URL", "amqp://sirius:sirius@localhost:5672/")
TIMEOUT = 10.0


def broker_available() -> bool:
    async def probe():
        connection = await aio_pika.connect(URL, timeout=2)
        await connection.close()
    try:
        asyncio.run(probe())
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not broker_available(), reason=f"RabbitMQ недоступен: {URL}")


@pytest.fixture
def storage(monkeypatch) -> InMemoryStorage:
    """Consumer'ы кухни и заказов берут репозитории из корня композиции, в тестах он работает в памяти."""
    fresh = InMemoryStorage()
    monkeypatch.setattr(dependencies, "memory_storage", fresh)
    monkeypatch.setattr(consumer_module, "RETRY_DELAY_SECONDS", 0.05)
    return fresh


@pytest.fixture
def topology():
    topology = Topology(prefix=f"test_{uuid.uuid4().hex[:8]}_")
    yield topology

    async def cleanup():
        connection = await aio_pika.connect(URL)
        async with connection:
            await topology.delete(await connection.channel())
    asyncio.run(cleanup())


@asynccontextmanager
async def broker(topology: Topology, *consumers: EventConsumer):
    """Объявляет топологию, запускает consumer'ы и отдаёт exchange для публикации."""
    stop = asyncio.Event()
    for c in consumers:
        c.topology = topology
    connection = await aio_pika.connect(URL)
    async with connection:
        channel = await connection.channel()
        exchange = await topology.declare(channel)
        tasks = [asyncio.create_task(c.run(URL, stop)) for c in consumers]
        try:
            yield channel, exchange
        finally:
            stop.set()
            await asyncio.gather(*tasks)


async def publish(exchange, event):
    await exchange.publish(
        event_message(event.event_id, event.ROUTING_KEY, event.to_payload(), event.occurred_at),
        routing_key=event.ROUTING_KEY,
    )


async def eventually(condition, timeout=TIMEOUT):
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("Не дождались обработки")
        await asyncio.sleep(0.05)


async def dead_letters(channel, topology, spec) -> list[aio_pika.abc.AbstractIncomingMessage]:
    queue = await channel.get_queue(topology.dead_letter_queue(spec))
    messages = []
    while message := await queue.get(fail=False):
        messages.append(message)
        await message.ack()
    return messages


def paid_order(storage, status=OrderStatus.PAID, total_cost=100.0):
    student = add_user(storage, balance=0.0)
    order = add_order(storage, student.id, add_menu_item(storage).id, status, total_cost)
    return student, order


def test_kitchen_consumer_queues_paid_order(storage, topology):
    _, order = paid_order(storage)

    async def scenario():
        async with broker(topology, kitchen_consumer.consumer) as (_, exchange):
            await publish(exchange, OrderPaid(order_id=order.id, customer_id=1, amount=100.0))
            await eventually(lambda: storage.kitchen_tickets)
    asyncio.run(scenario())

    [ticket] = storage.kitchen_tickets.values()
    assert (ticket.order_id, ticket.status) == (order.id, KitchenTicketStatus.QUEUED)


def test_redelivered_event_does_not_create_duplicate(storage, topology):
    _, order = paid_order(storage)
    event = OrderPaid(order_id=order.id, customer_id=1, amount=100.0)
    calls = []

    def counting(event, receipt):
        calls.append(receipt)
        return kitchen_consumer.on_order_paid(event, receipt)
    kitchen = EventConsumer("kitchen", KITCHEN, {OrderPaid: counting})

    async def scenario():
        async with broker(topology, kitchen) as (_, exchange):
            for _ in range(3):
                await publish(exchange, event)
            await eventually(lambda: len(calls) == 3)
    asyncio.run(scenario())

    assert len(storage.kitchen_tickets) == 1
    assert storage.receipts == {Receipt("kitchen", event.event_id)}


def test_one_event_reaches_kitchen_and_delivery_independently(storage, topology):
    courier = add_user(storage, role=Role.COURIER)
    _, order = paid_order(storage)

    def dispatch(event, receipt):
        result = DeliveryService(InMemoryDeliveryRepository(storage)).dispatch(event, receipt)
        return f"delivery {result.id}"
    delivery = EventConsumer("delivery", DELIVERY, {OrderPaid: dispatch})

    async def scenario():
        async with broker(topology, kitchen_consumer.consumer, delivery) as (_, exchange):
            await publish(exchange, OrderPaid(order_id=order.id, customer_id=1, amount=100.0))
            await eventually(lambda: storage.kitchen_tickets and storage.deliveries)
    asyncio.run(scenario())

    [delivery_row] = storage.deliveries.values()
    assert delivery_row.courier_id == courier.id
    assert {r.consumer for r in storage.receipts} == {"kitchen", "delivery"}


def test_broken_message_goes_to_dlq_and_queue_keeps_working(storage, topology):
    _, order = paid_order(storage)

    async def scenario():
        async with broker(topology, kitchen_consumer.consumer) as (channel, exchange):
            await exchange.publish(aio_pika.Message(b"not-json"), routing_key="order.paid")
            await publish(exchange, OrderPaid(order_id=order.id, customer_id=1, amount=100.0))
            await eventually(lambda: storage.kitchen_tickets)
            await asyncio.sleep(0.2)
            return await dead_letters(channel, topology, KITCHEN)
    [letter] = asyncio.run(scenario())

    assert letter.body == b"not-json"
    assert letter.headers["x-death"][0]["reason"] == "rejected"
    assert len(storage.kitchen_tickets) == 1


def test_failing_handler_retries_then_dlq_then_replay(storage, topology):
    _, order = paid_order(storage)
    event = OrderPaid(order_id=order.id, customer_id=1, amount=100.0)
    attempts = []

    def broken(event, receipt):
        attempts.append(time.monotonic())
        raise RuntimeError("БД недоступна")
    failing = EventConsumer("kitchen", KITCHEN, {OrderPaid: broken})

    async def fail():
        async with broker(topology, failing) as (channel, exchange):
            await exchange.publish(aio_pika.Message(b"not-json"), routing_key="order.paid")
            await publish(exchange, event)
            await eventually(lambda: len(attempts) == DELIVERY_LIMIT + 1)
            await asyncio.sleep(0.3)
            dlq = await channel.declare_queue(topology.dead_letter_queue(KITCHEN), passive=True)
            return dlq.declaration_result.message_count
    assert asyncio.run(fail()) == 2
    assert len(attempts) == DELIVERY_LIMIT + 1

    # Ошибку починили: сообщение возвращается из DLQ и обрабатывается обычным consumer'ом.
    # Битое сообщение остаётся в DLQ и не крутится по кругу.
    async def replay():
        async with broker(topology, kitchen_consumer.consumer) as (channel, _):
            result = await replay_dead_letters(KITCHEN, topology, URL)
            await eventually(lambda: storage.kitchen_tickets)
            left = await dead_letters(channel, topology, KITCHEN)
            return result, [m.body for m in left]
    assert asyncio.run(replay()) == ((1, 1), [b"not-json"])
    assert [t.order_id for t in storage.kitchen_tickets.values()] == [order.id]


class MemoryOutboxStore:
    """Outbox хранилища в памяти для релея: он не знает, откуда события."""

    def __init__(self, storage: InMemoryStorage):
        self.storage = storage
        self.published: set[str] = set()

    def fetch_pending(self, limit):
        return [
            PendingEvent(i, e.event_id, e.ROUTING_KEY, e.to_payload(), e.occurred_at)
            for i, e in enumerate(self.storage.outbox) if e.event_id not in self.published
        ][:limit]

    def mark_published(self, ids):
        self.published.update(self.storage.outbox[i].event_id for i in ids)

    def record_failure(self, outbox_id, error):
        pass

    def pending(self):
        return len(self.storage.outbox) - len(self.published), None


def test_saga_through_broker_refunds_when_no_courier(storage, topology):
    """Оплата → релей → кухня и доставка → DeliveryFailed → заказы → OrderCancelled → кухня."""
    from app.modules.orders.repository import InMemoryOrderRepository
    from app.modules.orders.service import OrderService
    from tests.conftest import RecordingNotifier

    student, order = paid_order(storage, status=OrderStatus.PROCESSING, total_cost=300.0)

    def dispatch(event, receipt):
        DeliveryService(InMemoryDeliveryRepository(storage)).dispatch(event, receipt)
        return "dispatched"
    delivery = EventConsumer("delivery", DELIVERY, {OrderPaid: dispatch})

    async def scenario():
        stop = asyncio.Event()
        relay = OutboxRelay(MemoryOutboxStore(storage), topology, URL)
        async with broker(topology, kitchen_consumer.consumer, delivery, orders_consumer.consumer):
            relay_task = asyncio.create_task(relay.run(stop))
            OrderService(InMemoryOrderRepository(storage), RecordingNotifier()).pay_order(order.id, student)
            await eventually(lambda: any(
                t.status == KitchenTicketStatus.CANCELLED for t in storage.kitchen_tickets.values()
            ))
            stop.set()
            await relay_task
    asyncio.run(scenario())

    assert [e.ROUTING_KEY for e in storage.outbox] == ["order.paid", "delivery.failed", "order.cancelled"]
    assert storage.orders[order.id].status == OrderStatus.CANCELLED
    assert storage.users[student.id].balance == 300.0
    paid, failed, cancelled = (e.event_id for e in storage.outbox)
    assert storage.receipts == {
        Receipt("kitchen", paid), Receipt("delivery", paid), Receipt("orders", failed), Receipt("kitchen", cancelled),
    }
