"""
Фоновые задачи после оформления заказа: PDF-чек, email и SMS.

В задачу передаётся только id заказа. Контакты читаются из БД в момент выполнения:
персональные данные не лежат в брокере и не видны во Flower.
"""
import logging
from collections.abc import Callable

from celery import Task

from app.core.celery_app import celery_app
from app.domain.entities import Order, User
from app.modules.orders.repository import SqlAlchemyOrderRepository
from app.tasks import stubs
from app.tasks.dead_letters import send_to_dead_letters
from app.tasks.journal import TaskJournal, TaskStatus, session_scope

logger = logging.getLogger(__name__)

# Повтор через 1, 2, 4 секунды. Jitter делает задержку случайной в пределах этого значения:
# после сбоя провайдера тысячи задач не придут к нему в одну и ту же секунду.
RETRY_POLICY = dict(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)


class OrderTask(Task):
    """Задача заказа. После последней неудачной попытки уходит в Dead Letter Queue."""

    kind: str

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        order_id = args[0] if args else kwargs["order_id"]
        logger.error("Order %s %s failed after %s retries, moved to DLQ", order_id, self.kind, self.request.retries)
        send_to_dead_letters(self.name, task_id, args, kwargs, repr(exc))
        with session_scope() as db:
            TaskJournal(db).finish(order_id, self.kind, TaskStatus.DEAD, error=repr(exc))


def run_once(task: OrderTask, order_id: int, action: Callable[[Order, User], None]) -> str:
    with session_scope() as db:
        journal = TaskJournal(db)
        if not journal.claim(order_id, task.kind):
            logger.info("Order %s %s already done or in progress, skipped", order_id, task.kind)
            return f"{task.kind} for order {order_id}: skipped"

        orders = SqlAlchemyOrderRepository(db)
        order = orders.get_order(order_id)
        try:
            action(order, orders.get_user_by_id(order.user_id))
        except Exception as exc:
            journal.finish(order_id, task.kind, TaskStatus.FAILED, error=repr(exc))
            raise
        journal.finish(order_id, task.kind, TaskStatus.DONE)
    return f"{task.kind} for order {order_id}: done"


@celery_app.task(base=OrderTask, bind=True, kind="receipt_pdf", **RETRY_POLICY)
def generate_order_pdf(self, order_id: int) -> str:
    return run_once(self, order_id, lambda order, customer: stubs.render_receipt_pdf(order.id))


@celery_app.task(base=OrderTask, bind=True, kind="email", **RETRY_POLICY)
def send_order_email(self, order_id: int) -> str:
    return run_once(self, order_id, lambda order, customer: stubs.send_email(order.id, customer.email))


@celery_app.task(base=OrderTask, bind=True, kind="sms", **RETRY_POLICY)
def send_order_sms(self, order_id: int) -> str:
    return run_once(
        self,
        order_id,
        lambda order, customer: stubs.send_sms(order.id, customer.phone, attempt=self.request.retries),
    )
