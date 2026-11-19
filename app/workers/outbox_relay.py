"""
Релей Transactional Outbox: читает неотправленные события из outbox_events и публикует их в RabbitMQ.
Запрос оплаты брокера не ждёт. Брокер лежит: события копятся в таблице и уходят, когда он поднимется.

    python -m app.workers.outbox_relay
    python -m app.workers.outbox_relay --poll-only   # без LISTEN, для замера «до»

Запускается в одном экземпляре. Второй экземпляр отправит часть событий дважды,
их отсеет Inbox получателей, но порядок событий одного заказа может нарушиться.
"""
import argparse
import asyncio
import logging
import signal
from contextlib import suppress
from datetime import UTC, datetime

import aio_pika
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from opentelemetry import trace
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import SpanKind

from app.core.config import settings
from app.core.observability import configure_worker
from app.core.rabbitmq import Topology, event_message
from app.database import database_url
from app.outbox import NOTIFY_CHANNEL, OutboxStore

logger = logging.getLogger("outbox")

BATCH_SIZE = 100
# NOTIFY будит релей сразу после COMMIT. Опрос по таймеру страхует, если уведомление потерялось.
POLL_SECONDS = 1.0
RECONNECT_SECONDS = 2.0
PUBLISH_TIMEOUT_SECONDS = 5.0


class OutboxWakeup:
    """LISTEN outbox_events на отдельном соединении с PostgreSQL."""

    def __init__(self):
        self.signal = asyncio.Event()
        self.connection = None

    def start(self) -> None:
        dsn = database_url().set(drivername="postgresql").render_as_string(hide_password=False)
        try:
            self.connection = psycopg2.connect(dsn)
            self.connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            self.connection.cursor().execute(f"LISTEN {NOTIFY_CHANNEL}")
        except psycopg2.Error as e:
            logger.warning("LISTEN failed (%s), polling every %.0f s", e, POLL_SECONDS)
            self.connection = None
            return
        asyncio.get_running_loop().add_reader(self.connection.fileno(), self._on_readable)

    def _on_readable(self) -> None:
        try:
            self.connection.poll()
        except psycopg2.Error as e:
            logger.warning("LISTEN connection lost (%s), polling every %.0f s", e, POLL_SECONDS)
            asyncio.get_running_loop().remove_reader(self.connection.fileno())
            self.connection = None
            return
        if self.connection.notifies:
            self.connection.notifies.clear()
            self.signal.set()

    async def wait(self, timeout: float) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(self.signal.wait(), timeout)
        self.signal.clear()


class OutboxRelay:
    def __init__(self, store: OutboxStore, topology: Topology = Topology(), url: str | None = None, listen: bool = True):
        self.store = store
        self.topology = topology
        self.url = url or settings.RABBITMQ_URL
        self.listen = listen

    async def publish_pending(self, exchange: aio_pika.abc.AbstractExchange) -> int:
        """Отправляет пачку событий по порядку. На первой ошибке останавливается: порядок важнее скорости."""
        events = await asyncio.to_thread(self.store.fetch_pending, BATCH_SIZE)
        published = []
        try:
            for event in events:
                headers = {}
                correlation_id = event.payload.get("correlation_id")
                parent = extract({"traceparent": event.payload["traceparent"]}) if event.payload.get("traceparent") else None
                with trace.get_tracer("sirius.eda").start_as_current_span(
                    f"rabbitmq.publish {event.routing_key}", context=parent, kind=SpanKind.PRODUCER,
                ) as span:
                    span.set_attribute("messaging.system", "rabbitmq")
                    span.set_attribute("messaging.destination.name", event.routing_key)
                    span.set_attribute("messaging.message.id", event.event_id)
                    if correlation_id:
                        span.set_attribute("app.correlation_id", correlation_id)
                        headers["X-Correlation-ID"] = correlation_id
                    inject(headers)
                    message = event_message(
                        event.event_id, event.routing_key, event.payload, event.created_at, headers,
                    )
                    # Span охватывает сетевую публикацию; publisher confirm значит, что брокер записал сообщение.
                    await exchange.publish(message, routing_key=event.routing_key, timeout=PUBLISH_TIMEOUT_SECONDS)
                published.append(event.id)
        except Exception as e:
            await asyncio.to_thread(self.store.record_failure, events[len(published)].id, repr(e))
            raise
        finally:
            # Отметку ставим после подтверждения брокера. Падение между ними даст повторную отправку,
            # а не потерю: повтор отсеет Inbox получателя.
            if published:
                await asyncio.to_thread(self.store.mark_published, published)
        if events:
            lag = (datetime.now(UTC) - events[0].created_at).total_seconds() * 1000
            logger.info("published %d events, oldest waited %.0f ms", len(events), lag)
        return len(events)

    async def run(self, stop: asyncio.Event) -> None:
        wakeup = OutboxWakeup()
        if self.listen:
            wakeup.start()
        while not stop.is_set():
            try:
                connection = await aio_pika.connect(self.url)
                async with connection:
                    # on_return_raises: событие без единой очереди не считается отправленным.
                    channel = await connection.channel(on_return_raises=True)
                    exchange = await self.topology.declare(channel)
                    logger.info("connected to RabbitMQ, relaying outbox")
                    while not stop.is_set():
                        if await self.publish_pending(exchange) < BATCH_SIZE:
                            await wakeup.wait(POLL_SECONDS)
            except Exception as e:
                try:
                    pending, _ = await asyncio.to_thread(self.store.pending)
                except Exception:
                    pending = "?"
                logger.warning(
                    "relay paused (%s: %s), %s events wait in outbox, retry in %.0f s",
                    e.__class__.__name__, e, pending, RECONNECT_SECONDS,
                )
                with suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), RECONNECT_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.workers.outbox_relay")
    parser.add_argument("--poll-only", action="store_true", help="не слушать NOTIFY, только опрос раз в секунду")
    args = parser.parse_args()
    configure_worker("sirius-outbox")
    logging.getLogger("aio_pika").setLevel(logging.ERROR)
    logging.getLogger("aiormq").setLevel(logging.ERROR)

    async def run() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        await OutboxRelay(OutboxStore(), listen=not args.poll_only).run(stop)
        logger.info("relay stopped")

    asyncio.run(run())


if __name__ == "__main__":
    main()
