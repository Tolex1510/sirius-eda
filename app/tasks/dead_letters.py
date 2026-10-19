"""
Dead Letter Queue: задачи, которые не выполнились после всех ретраев.
Лежат в очереди dlq брокера, пока их не разберут вручную:

    python -m app.cli dlq-list
    python -m app.cli dlq-replay
"""
from datetime import UTC, datetime

from app.core.celery_app import DEAD_LETTER_QUEUE, celery_app


def send_to_dead_letters(task_name: str, task_id: str, args: list, kwargs: dict, error: str) -> None:
    letter = {
        "task": task_name,
        "task_id": task_id,
        "args": list(args),
        "kwargs": kwargs,
        "error": error[:500],
        "failed_at": datetime.now(UTC).isoformat(),
    }
    with celery_app.producer_or_acquire() as producer:
        producer.publish(
            letter,
            exchange=DEAD_LETTER_QUEUE.exchange,
            routing_key=DEAD_LETTER_QUEUE.routing_key,
            declare=[DEAD_LETTER_QUEUE],
            serializer="json",
            retry=True,
        )


def list_dead_letters() -> list[dict]:
    """Читает очередь, не удаляя сообщения: без подтверждения брокер возвращает их обратно."""
    with celery_app.connection_for_read() as connection:
        queue = connection.SimpleQueue(DEAD_LETTER_QUEUE)
        messages = []
        while True:
            try:
                messages.append(queue.get(block=False))
            except queue.Empty:
                break
        letters = [message.payload for message in messages]
        for message in messages:
            message.requeue()
        queue.close()
    return letters


def replay_dead_letters() -> int:
    """Ставит задачи из DLQ обратно в рабочую очередь с новым запасом ретраев."""
    replayed = 0
    with celery_app.connection_for_write() as connection:
        queue = connection.SimpleQueue(DEAD_LETTER_QUEUE)
        while True:
            try:
                message = queue.get(block=False)
            except queue.Empty:
                break
            letter = message.payload
            celery_app.send_task(letter["task"], args=letter["args"], kwargs=letter["kwargs"])
            message.ack()
            replayed += 1
        queue.close()
    return replayed
