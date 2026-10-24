"""
Инфраструктура RabbitMQ: топология, подключение, формат сообщения.
Топологию объявляют все процессы одинаково, поэтому неважно, кто стартовал первым:
релей не отправит событие в exchange, у которого ещё нет очередей.
"""
import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime

import aio_pika
from aio_pika import DeliveryMode, ExchangeType
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractRobustConnection

from app.core.config import settings
from app.domain.events import DeliveryFailed, OrderCancelled, OrderPaid

logger = logging.getLogger(__name__)

# Сколько неудачных доставок одного сообщения терпит очередь. Дальше RabbitMQ сам перекладывает его в DLQ.
DELIVERY_LIMIT = 3
CONNECT_RETRY_SECONDS = 2.0


@dataclass(frozen=True)
class QueueSpec:
    name: str
    routing_keys: tuple[str, ...]


KITCHEN = QueueSpec("kitchen", (OrderPaid.ROUTING_KEY, OrderCancelled.ROUTING_KEY))
DELIVERY = QueueSpec("delivery", (OrderPaid.ROUTING_KEY,))
ORDERS = QueueSpec("orders", (DeliveryFailed.ROUTING_KEY,))
QUEUES = (KITCHEN, DELIVERY, ORDERS)


@dataclass(frozen=True)
class Topology:
    """Имена exchange и очередей. Префикс нужен интеграционным тестам, чтобы не трогать рабочие очереди."""
    prefix: str = ""

    @property
    def exchange(self) -> str:
        return f"{self.prefix}sirius_events"

    @property
    def dead_letter_exchange(self) -> str:
        return f"{self.prefix}sirius_dlx"

    def queue(self, spec: QueueSpec) -> str:
        return f"{self.prefix}{spec.name}_queue"

    def dead_letter_queue(self, spec: QueueSpec) -> str:
        return f"{self.prefix}{spec.name}_dlq"

    async def declare(self, channel: AbstractChannel) -> AbstractExchange:
        exchange = await channel.declare_exchange(self.exchange, ExchangeType.TOPIC, durable=True)
        dlx = await channel.declare_exchange(self.dead_letter_exchange, ExchangeType.DIRECT, durable=True)
        for spec in QUEUES:
            dlq = await channel.declare_queue(self.dead_letter_queue(spec), durable=True)
            await dlq.bind(dlx, routing_key=dlq.name)
            queue = await channel.declare_queue(self.queue(spec), durable=True, arguments={
                # Quorum-очередь считает доставки сама и после лимита отдаёт сообщение в DLX.
                # У классической очереди счётчика нет: битое сообщение крутилось бы вечно.
                "x-queue-type": "quorum",
                "x-delivery-limit": DELIVERY_LIMIT,
                "x-dead-letter-exchange": dlx.name,
                "x-dead-letter-routing-key": dlq.name,
            })
            for routing_key in spec.routing_keys:
                await queue.bind(exchange, routing_key=routing_key)
        return exchange

    async def delete(self, channel: AbstractChannel) -> None:
        for spec in QUEUES:
            await channel.queue_delete(self.queue(spec))
            await channel.queue_delete(self.dead_letter_queue(spec))
        await channel.exchange_delete(self.exchange)
        await channel.exchange_delete(self.dead_letter_exchange)


async def connect(url: str | None = None) -> AbstractRobustConnection:
    """Robust-подключение само восстанавливает каналы и подписки после рестарта RabbitMQ. Ждёт брокер при старте."""
    while True:
        try:
            # По умолчанию переподключение раз в 5 с: после рестарта брокера очередь стояла бы лишние секунды.
            return await aio_pika.connect_robust(url or settings.RABBITMQ_URL, reconnect_interval=CONNECT_RETRY_SECONDS)
        except (ConnectionError, aio_pika.exceptions.AMQPConnectionError) as e:
            logger.warning("RabbitMQ unavailable (%s), retry in %.0f s", e, CONNECT_RETRY_SECONDS)
            await asyncio.sleep(CONNECT_RETRY_SECONDS)


def event_message(event_id: str, routing_key: str, payload: dict, occurred_at: datetime) -> aio_pika.Message:
    return aio_pika.Message(
        body=json.dumps(payload, ensure_ascii=False).encode(),
        content_type="application/json",
        message_id=event_id,
        type=routing_key,
        timestamp=occurred_at,
        # Сообщение пишется на диск и переживает рестарт брокера.
        delivery_mode=DeliveryMode.PERSISTENT,
    )
