"""
Фоновые задачи заказа: идемпотентность, ретраи, DLQ и периодические задачи.
Брокер в памяти, БД на SQLite, задержки заглушек убраны. Redis и PostgreSQL не нужны.
"""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from kombu.exceptions import OperationalError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database
from app.core.celery_app import DEAD_LETTER_QUEUE, DEFAULT_QUEUE, celery_app
from app.core.config import settings
from app.database import Base
from app.domain.entities import Role
from app.models import MenuItem, Order, Role as RoleModel, TaskLog, User
from app.modules.orders.notifier import CeleryOrderNotifier, InlineOrderNotifier
from app.tasks import maintenance, orders, stubs
from app.tasks.dead_letters import list_dead_letters, replay_dead_letters
from app.tasks.journal import STALE_AFTER, TaskJournal, TaskStatus


@pytest.fixture(autouse=True)
def broker(monkeypatch):
    monkeypatch.setitem(celery_app.conf, "broker_url", "memory://")
    with celery_app.connection_for_write() as connection:
        for queue in (DEFAULT_QUEUE, DEAD_LETTER_QUEUE):
            connection.SimpleQueue(queue).clear()


@pytest.fixture(autouse=True)
def provider_calls(monkeypatch) -> list[str]:
    """Вызовы внешних сервисов без задержек. Сбои по умолчанию выключены."""
    calls = []
    monkeypatch.setattr(stubs, "time", SimpleNamespace(sleep=lambda seconds: None))
    for name in ("render_receipt_pdf", "send_email", "send_sms"):
        original = getattr(stubs, name)
        monkeypatch.setattr(stubs, name, lambda *a, _f=original, _n=name, **kw: calls.append(_n) or _f(*a, **kw))
    monkeypatch.setattr(settings, "FAKE_EMAIL_FAIL_EVERY", 0)
    monkeypatch.setattr(settings, "FAKE_SMS_FLAKY_EVERY", 0)
    return calls


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "SessionLocal", session_factory)
    session = session_factory()
    session.add_all(RoleModel(name=name) for name in Role.ALL)
    session.commit()
    yield session
    session.close()


def make_order(db, phone: str | None = "+79001234567", created_at: datetime | None = None) -> int:
    role = db.query(RoleModel).filter_by(name=Role.STUDENT).one()
    user = User(email=f"student{db.query(User).count()}@sirius.ru", phone=phone, balance=0, role_id=role.id)
    item = MenuItem(name=f"Плов {db.query(MenuItem).count()}", price=150)
    db.add_all([user, item])
    db.flush()
    order = Order(user_id=user.id, item_id=item.id, quantity=1, status="processing", total_cost=150,
                  created_at=created_at or datetime.now(UTC))
    db.add(order)
    db.commit()
    return order.id


def log_of(db, order_id: int, kind: str) -> TaskLog:
    db.expire_all()
    return db.query(TaskLog).filter_by(order_id=order_id, kind=kind).one()


def queued_messages(queue) -> list:
    with celery_app.connection_for_read() as connection:
        simple = connection.SimpleQueue(queue)
        messages = []
        while True:
            try:
                messages.append(simple.get(block=False))
            except simple.Empty:
                return messages


def test_task_runs_once_even_if_started_twice(db, provider_calls):
    order_id = make_order(db)

    first = orders.generate_order_pdf.apply(args=[order_id]).get()
    second = orders.generate_order_pdf.apply(args=[order_id]).get()

    assert first == f"receipt_pdf for order {order_id}: done"
    assert second == f"receipt_pdf for order {order_id}: skipped"
    assert provider_calls == ["render_receipt_pdf"]
    assert log_of(db, order_id, "receipt_pdf").status == TaskStatus.DONE


def test_flaky_provider_succeeds_on_retry(db, provider_calls, monkeypatch):
    order_id = make_order(db)
    monkeypatch.setattr(settings, "FAKE_SMS_FLAKY_EVERY", order_id)

    result = orders.send_order_sms.apply(args=[order_id])

    assert result.successful()
    assert provider_calls == ["send_sms", "send_sms"]
    log = log_of(db, order_id, "sms")
    assert (log.status, log.attempts) == (TaskStatus.DONE, 2)


def test_task_goes_to_dlq_after_three_retries(db, provider_calls, monkeypatch):
    order_id = make_order(db)
    monkeypatch.setattr(settings, "FAKE_EMAIL_FAIL_EVERY", 1)

    result = orders.send_order_email.apply(args=[order_id])

    assert result.failed()
    assert provider_calls == ["send_email"] * 4
    log = log_of(db, order_id, "email")
    assert (log.status, log.attempts) == (TaskStatus.DEAD, 4)
    assert "Email service unavailable" in log.error
    [letter] = list_dead_letters()
    assert (letter["task"], letter["args"]) == ("app.tasks.orders.send_order_email", [order_id])


def test_listing_dlq_does_not_remove_letters(db, monkeypatch):
    monkeypatch.setattr(settings, "FAKE_EMAIL_FAIL_EVERY", 1)
    orders.send_order_email.apply(args=[make_order(db)])

    assert len(list_dead_letters()) == 1
    assert len(list_dead_letters()) == 1


def test_replay_moves_letters_back_to_work_queue(db, monkeypatch):
    order_id = make_order(db)
    monkeypatch.setattr(settings, "FAKE_EMAIL_FAIL_EVERY", 1)
    orders.send_order_email.apply(args=[order_id])

    assert replay_dead_letters() == 1

    assert list_dead_letters() == []
    [message] = queued_messages(DEFAULT_QUEUE)
    assert message.headers["task"] == "app.tasks.orders.send_order_email"
    assert message.payload[0] == [order_id]


def test_dead_task_can_run_again_after_replay(db, provider_calls, monkeypatch):
    order_id = make_order(db)
    monkeypatch.setattr(settings, "FAKE_EMAIL_FAIL_EVERY", 1)
    orders.send_order_email.apply(args=[order_id])
    monkeypatch.setattr(settings, "FAKE_EMAIL_FAIL_EVERY", 0)

    assert orders.send_order_email.apply(args=[order_id]).get().endswith("done")
    assert log_of(db, order_id, "email").status == TaskStatus.DONE


def test_task_in_progress_is_not_taken_twice(db):
    journal = TaskJournal(db)
    order_id = make_order(db)

    assert journal.claim(order_id, "email") is True
    assert journal.claim(order_id, "email") is False


def test_task_abandoned_by_dead_worker_is_taken_over(db):
    journal = TaskJournal(db)
    order_id = make_order(db)
    journal.claim(order_id, "email")
    db.query(TaskLog).update({"updated_at": datetime.now(UTC) - STALE_AFTER - timedelta(seconds=1)})
    db.commit()

    assert journal.claim(order_id, "email") is True
    assert log_of(db, order_id, "email").attempts == 2


def test_notifier_sends_only_order_id_to_broker(db):
    order_id = make_order(db)
    customer = SimpleNamespace(id=1, email="student@sirius.ru", phone="+79001234567")

    CeleryOrderNotifier().order_created(order_id, customer)

    messages = queued_messages(DEFAULT_QUEUE)
    assert sorted(m.headers["task"].rsplit(".", 1)[1] for m in messages) == [
        "generate_order_pdf", "send_order_email", "send_order_sms",
    ]
    # В брокер и во Flower не попадают email и телефон.
    assert all(m.payload[0] == [order_id] for m in messages)


def test_notifier_skips_sms_without_phone(db):
    CeleryOrderNotifier().order_created(make_order(db), SimpleNamespace(id=1, email="a@b.ru", phone=None))

    assert len(queued_messages(DEFAULT_QUEUE)) == 2


def test_order_survives_broker_outage(monkeypatch, caplog):
    def broker_down(*args, **kwargs):
        raise OperationalError("Connection refused")

    monkeypatch.setattr(orders.generate_order_pdf, "delay", broker_down)

    CeleryOrderNotifier().order_created(1, SimpleNamespace(id=1, email="a@b.ru", phone=None))

    assert "broker unavailable" in caplog.text


def test_inline_notifier_does_everything_in_request(provider_calls, monkeypatch):
    monkeypatch.setattr(settings, "FAKE_EMAIL_FAIL_EVERY", 1)

    InlineOrderNotifier().order_created(1, SimpleNamespace(id=1, email="a@b.ru", phone="+79001234567"))

    assert provider_calls == ["render_receipt_pdf", "send_email"]


def test_lost_tasks_are_requeued(db, monkeypatch):
    monkeypatch.setitem(celery_app.conf, "task_always_eager", True)
    lost = make_order(db, created_at=datetime.now(UTC) - timedelta(minutes=10))
    fresh = make_order(db)
    too_old = make_order(db, created_at=datetime.now(UTC) - timedelta(days=1))
    no_phone = make_order(db, phone=None, created_at=datetime.now(UTC) - timedelta(minutes=10))

    assert maintenance.requeue_lost_order_tasks.apply().get() == 5

    assert [log.status for log in db.query(TaskLog).filter_by(order_id=lost)] == [TaskStatus.DONE] * 3
    assert db.query(TaskLog).filter_by(order_id=no_phone).count() == 2
    assert db.query(TaskLog).filter(TaskLog.order_id.in_([fresh, too_old])).count() == 0
    assert maintenance.requeue_lost_order_tasks.apply().get() == 0


def test_cleanup_removes_only_old_logs(db):
    journal = TaskJournal(db)
    old, recent = make_order(db), make_order(db)
    journal.claim(old, "email")
    journal.claim(recent, "email")
    db.query(TaskLog).filter_by(order_id=old).update({"created_at": datetime.now(UTC) - timedelta(days=31)})
    db.commit()

    assert maintenance.cleanup_task_logs.apply().get() == 1
    assert [log.order_id for log in db.query(TaskLog)] == [recent]


def test_beat_schedule_points_to_registered_tasks():
    schedule = celery_app.conf.beat_schedule

    assert schedule["refresh-order-stats"]["schedule"] == 60.0
    assert {entry["task"] for entry in schedule.values()} <= set(celery_app.tasks)


def test_dead_letter_queue_is_not_consumed_by_workers():
    assert [queue.name for queue in celery_app.conf.task_queues] == ["default"]
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.accept_content == ["json"]


def test_unpaid_external_order_does_not_generate_receipt_or_recovery_tasks(db, provider_calls):
    order_id = make_order(db, created_at=datetime.now(UTC) - timedelta(minutes=5))
    db.query(Order).filter(Order.id == order_id).update({'payment_source': 'gateway'})
    db.commit()
    result = orders.generate_order_pdf.apply(args=[order_id]).get()
    assert 'skipped' in result
    assert provider_calls == []
    assert TaskJournal(db).orders_without('receipt_pdf', datetime.now(UTC) - timedelta(hours=1), datetime.now(UTC)) == []
