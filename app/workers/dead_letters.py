"""
Разбор DLQ событий: посмотреть, почему сообщение не обработано, и вернуть его в работу.
Вызывается из app/cli.py: events-dlq и events-dlq-replay.
"""
from dataclasses import dataclass

import aio_pika

from app.core.rabbitmq import QUEUES, QueueSpec, Topology, connect

PEEK_LIMIT = 20


@dataclass
class DeadLetter:
    queue: str
    event_type: str | None
    message_id: str | None
    reason: str
    body: str


def _describe(queue: str, message: aio_pika.abc.AbstractIncomingMessage) -> DeadLetter:
    death = ((message.headers or {}).get("x-death") or [{}])[0]
    return DeadLetter(
        queue=queue,
        event_type=message.type,
        message_id=message.message_id,
        # rejected: битое сообщение отклонено сразу; delivery_limit: исчерпаны попытки.
        reason=str(death.get("reason", "?")),
        body=message.body.decode(errors="replace")[:200],
    )


async def list_dead_letters(topology: Topology = Topology(), url: str | None = None) -> dict[str, list[DeadLetter]]:
    """Сообщения остаются в DLQ: после просмотра все возвращаются обратно в том же порядке."""
    result = {}
    connection = await connect(url)
    async with connection:
        channel = await connection.channel()
        await topology.declare(channel)
        for spec in QUEUES:
            queue = await channel.get_queue(topology.dead_letter_queue(spec))
            taken = []
            while len(taken) < PEEK_LIMIT and (message := await queue.get(fail=False)):
                taken.append(message)
            result[queue.name] = [_describe(queue.name, m) for m in taken]
            # Закрытие канала вернёт неподтверждённые сообщения. Явный nack делает это сразу.
            for message in reversed(taken):
                await message.nack(requeue=True)
    return result


async def replay_dead_letters(
    spec: QueueSpec, topology: Topology = Topology(), url: str | None = None,
) -> tuple[int, int]:
    """
    Возвращает сообщения в очередь одного получателя, а не в exchange: остальные их уже обработали.
    Битые сообщения остаются в DLQ: повтор их не исправит. Возвращает (возвращено, оставлено).
    """
    connection = await connect(url)
    async with connection:
        channel = await connection.channel()
        await topology.declare(channel)
        dlq = await channel.declare_queue(topology.dead_letter_queue(spec), passive=True)
        # Только то, что лежало в DLQ на старте: снова упавшее сообщение вернётся в DLQ и не должно браться второй раз.
        taken = []
        while len(taken) < dlq.declaration_result.message_count and (message := await dlq.get(fail=False)):
            taken.append(message)
        kept = [m for m in taken if _describe(dlq.name, m).reason == "rejected"]
        for message in taken:
            if message in kept:
                continue
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=message.body,
                    content_type=message.content_type,
                    message_id=message.message_id,
                    type=message.type,
                    timestamp=message.timestamp,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=topology.queue(spec),
            )
            await message.ack()
        for message in reversed(kept):
            await message.nack(requeue=True)
    return len(taken) - len(kept), len(kept)
