"""OrderCancelled доставляется настоящим RabbitMQ; шлюз и Celery управляемые."""
import asyncio
from unittest.mock import Mock
import pytest
from sqlalchemy import select
from app.core.rabbitmq import PAYMENTS
from app.domain.events import OrderCancelled
from app.models import OutboxEvent
from app.workers.consumer import EventConsumer
from app.workers import payments_consumer
from tests.test_payments import checkout, succeed, world
from tests.test_events_rabbitmq import broker_available, broker, publish, eventually, topology

pytestmark = pytest.mark.skipif(not broker_available(), reason='RabbitMQ недоступен')


def test_order_cancelled_refunds_once_through_payment_consumer(world, topology, monkeypatch):
    sessions, service, alice, *_ = world
    order, payment = checkout(world)
    succeed(service, payment)
    service.repository.cancel(alice, order.id)
    with sessions() as db:
        event = OrderCancelled.from_payload(db.scalar(select(OutboxEvent).where(
            OutboxEvent.routing_key == 'order.cancelled')).payload)
    monkeypatch.setattr(payments_consumer, 'payment_service', lambda: service)
    original_refund = service.gateway.refund
    refunds = Mock(wraps=original_refund)
    service.gateway.refund = refunds
    scheduled = []
    def run_payment(payment_id):
        service.sync(service.repository.get(payment_id))
        scheduled.append(payment_id)
    monkeypatch.setattr(payments_consumer.sync_payment, 'delay', run_payment)
    handled = []
    def handler(event, receipt):
        try:
            return payments_consumer.on_order_cancelled(event, receipt)
        finally:
            handled.append(receipt)
    consumer = EventConsumer('payments', PAYMENTS, {OrderCancelled: handler})

    async def scenario():
        async with broker(topology, consumer) as (_, exchange):
            for n in range(3):
                await publish(exchange, event)
                await eventually(lambda: len(handled) >= n + 1)
    asyncio.run(scenario())
    assert scheduled == [payment.id]
    assert refunds.call_count == 1
    assert service.repository.get(payment.id).refund_status == 'succeeded'
