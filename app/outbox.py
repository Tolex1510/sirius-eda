"""
Transactional Outbox и Inbox в PostgreSQL, общие для SQL-репозиториев всех модулей.
Событие и отметка об обработке добавляются в ту же сессию, что и данные, и коммитятся вместе с ними.
"""
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.domain.events import Event, Receipt
from app.domain.exceptions import AlreadyProcessedError
from app.models import OutboxEvent, ProcessedEvent
from app.core.observability import correlation_id_from_context, current_traceparent

NOTIFY_CHANNEL = "outbox_events"


def add_to_outbox(db: Session, event: Event) -> None:
    payload = event.to_payload()
    correlation_id = event.correlation_id or correlation_id_from_context()
    traceparent = current_traceparent()
    if correlation_id:
        payload["correlation_id"] = correlation_id
    if traceparent:
        payload["traceparent"] = traceparent
    db.add(OutboxEvent(
        event_id=event.event_id,
        routing_key=event.ROUTING_KEY,
        payload=payload,
        created_at=event.occurred_at,
        attempts=0,
    ))
    if db.get_bind().dialect.name == "postgresql":
        # Postgres доставит NOTIFY только после COMMIT: релей не увидит событие раньше данных.
        db.execute(text(f"NOTIFY {NOTIFY_CHANNEL}"))


def add_receipt(db: Session, receipt: Receipt) -> None:
    db.add(ProcessedEvent(consumer=receipt.consumer, event_id=receipt.event_id))


def has_receipt(db: Session, receipt: Receipt) -> bool:
    return db.query(
        db.query(ProcessedEvent)
        .filter(ProcessedEvent.consumer == receipt.consumer, ProcessedEvent.event_id == receipt.event_id)
        .exists()
    ).scalar()


def commit_once(db: Session) -> None:
    """Коммит обработки события. Нарушение уникальности значит, что параллельная доставка успела первой."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AlreadyProcessedError("Событие уже обработано")


@dataclass(frozen=True)
class PendingEvent:
    id: int
    event_id: str
    routing_key: str
    payload: dict
    created_at: datetime


class OutboxStore:
    """Чтение outbox для релея. Работает в своих коротких сессиях: релей живёт долго."""

    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def fetch_pending(self, limit: int) -> list[PendingEvent]:
        with self.session_factory() as db:
            rows = (
                db.query(OutboxEvent)
                .filter(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.id)
                .limit(limit)
            )
            return [PendingEvent(r.id, r.event_id, r.routing_key, r.payload, r.created_at) for r in rows]

    def mark_published(self, ids: list[int]) -> None:
        with self.session_factory() as db:
            db.query(OutboxEvent).filter(OutboxEvent.id.in_(ids)).update(
                {"published_at": datetime.now(UTC), "attempts": OutboxEvent.attempts + 1, "last_error": None},
                synchronize_session=False,
            )
            db.commit()

    def record_failure(self, outbox_id: int, error: str) -> None:
        with self.session_factory() as db:
            db.query(OutboxEvent).filter(OutboxEvent.id == outbox_id).update(
                {"attempts": OutboxEvent.attempts + 1, "last_error": error[:500]},
                synchronize_session=False,
            )
            db.commit()

    def pending(self) -> tuple[int, datetime | None]:
        """Сколько событий ждёт отправки и когда появилось самое старое."""
        with self.session_factory() as db:
            return db.query(func.count(OutboxEvent.id), func.min(OutboxEvent.created_at)).filter(
                OutboxEvent.published_at.is_(None)
            ).one()
