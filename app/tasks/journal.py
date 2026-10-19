"""
Журнал фоновых задач в PostgreSQL: основа идемпотентности.
Задача сначала занимает запись (order_id, kind), потом работает. Занять уже выполненную
или выполняемую сейчас задачу нельзя, поэтому повтор не отправит второй чек или письмо.
"""
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, exists, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import database
from app.models import Order, TaskLog, User


class TaskStatus:
    STARTED = "started"
    DONE = "done"
    # Попытка упала, Celery повторит задачу.
    FAILED = "failed"
    # Все попытки исчерпаны, задача лежит в DLQ.
    DEAD = "dead"


# Задача не может выполняться дольше task_time_limit. Запись в started старше этого срока
# значит, что воркер умер посреди работы, и задачу можно взять заново.
STALE_AFTER = timedelta(minutes=2)


def _now() -> datetime:
    return datetime.now(UTC)


@contextmanager
def session_scope() -> Iterator[Session]:
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


class TaskJournal:
    def __init__(self, db: Session):
        self.db = db

    def claim(self, order_id: int, kind: str) -> bool:
        """True, если задачу нужно выполнить. False, если она уже сделана или выполняется."""
        now = _now()
        self.db.add(TaskLog(order_id=order_id, kind=kind, status=TaskStatus.STARTED, attempts=1,
                            created_at=now, updated_at=now))
        try:
            self.db.commit()
            return True
        except IntegrityError:
            self.db.rollback()

        # Запись уже есть. Условие в самом UPDATE: из двух параллельных попыток выиграет одна.
        claimable = or_(
            TaskLog.status.in_((TaskStatus.FAILED, TaskStatus.DEAD)),
            and_(TaskLog.status == TaskStatus.STARTED, TaskLog.updated_at < now - STALE_AFTER),
        )
        updated = (
            self.db.query(TaskLog)
            .filter(TaskLog.order_id == order_id, TaskLog.kind == kind, claimable)
            .update(
                {"status": TaskStatus.STARTED, "attempts": TaskLog.attempts + 1, "error": None, "updated_at": now},
                synchronize_session=False,
            )
        )
        self.db.commit()
        return updated == 1

    def finish(self, order_id: int, kind: str, status: str, error: str | None = None) -> None:
        self.db.query(TaskLog).filter(TaskLog.order_id == order_id, TaskLog.kind == kind).update(
            {"status": status, "error": error[:500] if error else None, "updated_at": _now()},
            synchronize_session=False,
        )
        self.db.commit()

    def get(self, order_id: int, kind: str) -> TaskLog | None:
        return self.db.query(TaskLog).filter(TaskLog.order_id == order_id, TaskLog.kind == kind).first()

    def orders_without(self, kind: str, created_from: datetime, created_to: datetime, with_phone: bool = False) -> list[int]:
        """Заказы, для которых задача ни разу не начиналась: её не удалось поставить в очередь."""
        query = self.db.query(Order.id).filter(
            Order.created_at >= created_from,
            Order.created_at < created_to,
            ~exists().where(TaskLog.order_id == Order.id, TaskLog.kind == kind),
        )
        if with_phone:
            query = query.join(User, User.id == Order.user_id).filter(User.phone.isnot(None))
        return [order_id for (order_id,) in query.order_by(Order.id)]

    def delete_older_than(self, cutoff: datetime) -> int:
        deleted = self.db.query(TaskLog).filter(TaskLog.created_at < cutoff).delete(synchronize_session=False)
        self.db.commit()
        return deleted
