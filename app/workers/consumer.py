"""
Общий цикл consumer'а. Разбор, идемпотентность, ретраи и DLQ одинаковы
для кухни, доставки и заказов, отличаются только обработчики событий.
"""
import asyncio
import json
import logging
import signal
import time
from collections.abc import Callable

from aio_pika.abc import AbstractIncomingMessage

from app.core.rabbitmq import DELIVERY_LIMIT, QueueSpec, Topology, connect
from app.domain.events import Event, Receipt, parse_event
from app.domain.exceptions import AlreadyProcessedError

logger = logging.getLogger("events")

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
        try:
            event = parse_event(json.loads(message.body))
        except ValueError as e:
            # Битое сообщение не исправится повтором: сразу в DLQ, очередь не блокируется.
            logger.warning("%s rejected %s to DLQ: %s", self.name, message.message_id or "message", e)
            await message.reject(requeue=False)
            return

        handler = self.handlers.get(type(event))
        if handler is None:
            await message.ack()
            return

        attempt = int((message.headers or {}).get("x-delivery-count", 0)) + 1
        try:
            outcome = await asyncio.to_thread(handler, event, Receipt(self.name, event.event_id))
        except AlreadyProcessedError:
            logger.info("%s %s %s duplicate, skipped", self.name, event.ROUTING_KEY, event.event_id[:8])
            await message.ack()
        except Exception:
            last = attempt > DELIVERY_LIMIT
            logger.exception(
                "%s %s %s attempt %d failed%s", self.name, event.ROUTING_KEY, event.event_id[:8], attempt,
                ", moved to DLQ" if last else "",
            )
            if not last:
                # Мгновенный повтор упрётся в ту же ошибку: даём БД или соседнему сервису подняться.
                await asyncio.sleep(min(RETRY_DELAY_SECONDS * 2 ** (attempt - 1), MAX_RETRY_DELAY_SECONDS))
            await message.nack(requeue=True)
        else:
            await message.ack()
            logger.info(
                "%s %s %s %s %.1f ms", self.name, event.ROUTING_KEY, event.event_id[:8], outcome,
                (time.perf_counter() - started) * 1000,
            )

    async def run(self, url: str | None = None, stop: asyncio.Event | None = None) -> None:
        connection = await connect(url)
        async with connection:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=PREFETCH)
            await self.topology.declare(channel)
            queue = await channel.get_queue(self.topology.queue(self.spec))
            await queue.consume(self.handle)
            logger.info("%s consumer listening on %s", self.name, queue.name)
            await (stop or asyncio.Event()).wait()
        # Неподтверждённые сообщения при закрытии канала вернутся в очередь: at-least-once.


def serve(consumer: EventConsumer) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logging.getLogger("aio_pika").setLevel(logging.WARNING)
    logging.getLogger("aiormq").setLevel(logging.WARNING)

    async def main() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        await consumer.run(stop=stop)
        logger.info("%s consumer stopped", consumer.name)

    asyncio.run(main())
