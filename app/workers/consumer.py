"""
Общий цикл consumer'а. Разбор, идемпотентность, ретраи и DLQ одинаковы
для кухни, доставки и заказов, отличаются только обработчики событий.
"""
import asyncio
import json
import signal
import time
from collections.abc import Callable

from aio_pika.abc import AbstractIncomingMessage
import structlog
from opentelemetry import trace
from opentelemetry.propagate import extract
from opentelemetry.trace import SpanKind, Status, StatusCode

from app.core.observability import configure_worker
from app.core.rabbitmq import DELIVERY_LIMIT, QueueSpec, Topology, connect
from app.domain.events import Event, Receipt, parse_event
from app.domain.exceptions import AlreadyProcessedError

logger = structlog.get_logger("events")

PREFETCH = 10
RETRY_DELAY_SECONDS = 1.0
MAX_RETRY_DELAY_SECONDS = 10.0

# Обработчик синхронный: он работает с БД через SQLAlchemy и выполняется в пуле потоков.
# Возвращает строку для лога.
Handler = Callable[[Event, Receipt], str]


class EventConsumer:
    def __init__(self, name: str, spec: QueueSpec, handlers: dict[type[Event], Handler], topology: Topology = Topology()):
        self.name = name
        self.spec = spec
        self.handlers = handlers
        self.topology = topology

    async def handle(self, message: AbstractIncomingMessage) -> None:
        started = time.perf_counter()
        headers = message.headers or {}
        try:
            event = parse_event(json.loads(message.body))
        except ValueError as e:
            # Битое сообщение не исправится повтором: сразу в DLQ, очередь не блокируется.
            logger.warning(
                "event_rejected", consumer=self.name, message_id=message.message_id or "message", error=str(e),
                correlation_id=headers.get("X-Correlation-ID", "unknown"),
            )
            await message.reject(requeue=False)
            return

        correlation_id = headers.get("X-Correlation-ID") or event.correlation_id or "unknown"
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id, consumer=self.name)
        parent = extract(headers)
        try:
            with trace.get_tracer("sirius.eda").start_as_current_span(
                f"rabbitmq.consume {event.ROUTING_KEY}", context=parent, kind=SpanKind.CONSUMER,
            ) as span:
                span.set_attribute("messaging.system", "rabbitmq")
                span.set_attribute("messaging.destination.name", self.spec.name)
                span.set_attribute("messaging.message.id", event.event_id)
                span.set_attribute("app.order_id", getattr(event, "order_id", 0))
                span.set_attribute("app.correlation_id", correlation_id)
                handler = self.handlers.get(type(event))
                if handler is None:
                    await message.ack()
                    return

                attempt = int(headers.get("x-delivery-count", 0)) + 1
                try:
                    outcome = await asyncio.to_thread(handler, event, Receipt(self.name, event.event_id))
                except AlreadyProcessedError:
                    logger.info("event_duplicate", event_type=event.ROUTING_KEY, event_id=event.event_id)
                    await message.ack()
                except Exception as error:
                    span.record_exception(error)
                    span.set_status(Status(StatusCode.ERROR, str(error)))
                    last = attempt > DELIVERY_LIMIT
                    logger.exception(
                        "event_processing_failed", event_type=event.ROUTING_KEY, event_id=event.event_id,
                        attempt=attempt, sent_to_dlq=last,
                    )
                    if not last:
                        await asyncio.sleep(min(RETRY_DELAY_SECONDS * 2 ** (attempt - 1), MAX_RETRY_DELAY_SECONDS))
                    await message.nack(requeue=True)
                else:
                    await message.ack()
                    logger.info(
                        "event_processed", event_type=event.ROUTING_KEY, event_id=event.event_id,
                        order_id=getattr(event, "order_id", None), outcome=outcome,
                        duration_ms=round((time.perf_counter() - started) * 1000, 1),
                    )
        finally:
            structlog.contextvars.clear_contextvars()

    async def run(self, url: str | None = None, stop: asyncio.Event | None = None) -> None:
        connection = await connect(url)
        async with connection:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=PREFETCH)
            await self.topology.declare(channel)
            queue = await channel.get_queue(self.topology.queue(self.spec))
            await queue.consume(self.handle)
            logger.info("consumer_started", consumer=self.name, queue=queue.name)
            await (stop or asyncio.Event()).wait()
        # Неподтверждённые сообщения при закрытии канала вернутся в очередь: at-least-once.


def serve(consumer: EventConsumer) -> None:
    configure_worker(f"sirius-{consumer.name}")
    import logging

    logging.getLogger("aio_pika").setLevel(logging.WARNING)
    logging.getLogger("aiormq").setLevel(logging.WARNING)

    async def main() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        await consumer.run(stop=stop)
        logger.info("consumer_stopped", consumer=consumer.name)

    asyncio.run(main())
