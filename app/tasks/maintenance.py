"""
Периодические задачи Celery Beat.
Beat только ставит их в очередь по расписанию, выполняет обычный воркер.
"""
import logging
from datetime import UTC, datetime, timedelta

from app.core.celery_app import celery_app
from app.dependencies import order_repository_scope
from app.modules.orders.service import OrderStatsService
from app.tasks.journal import TaskJournal, session_scope
from app.tasks.orders import generate_order_pdf, send_order_email, send_order_sms

logger = logging.getLogger(__name__)

TASK_LOG_RETENTION = timedelta(days=30)
# Задача могла просто не дойти до воркера из-за очереди. Через 2 минуты считаем её потерянной.
LOST_TASK_GRACE = timedelta(minutes=2)
LOST_TASK_WINDOW = timedelta(minutes=30)


@celery_app.task
def refresh_order_stats() -> list[dict]:
    with order_repository_scope() as repository:
        stats = OrderStatsService(repository).refresh(datetime.now(UTC).date())
    logger.info("Order stats refreshed: %s", ", ".join(f"{s.day} {s.orders} orders" for s in stats))
    return [{"day": s.day.isoformat(), "orders": s.orders, "revenue": s.revenue} for s in stats]


@celery_app.task
def cleanup_task_logs() -> int:
    with session_scope() as db:
        deleted = TaskJournal(db).delete_older_than(datetime.now(UTC) - TASK_LOG_RETENTION)
    logger.info("Task logs older than %s days deleted: %s", TASK_LOG_RETENTION.days, deleted)
    return deleted


@celery_app.task
def requeue_lost_order_tasks() -> int:
    """
    Досылает задачи заказов, которые не попали в очередь: в момент заказа брокер был недоступен.
    Повторная постановка безопасна. Если задача всё же была в очереди, журнал её пропустит.
    """
    now = datetime.now(UTC)
    requeued = 0
    with session_scope() as db:
        journal = TaskJournal(db)
        for task in (generate_order_pdf, send_order_email, send_order_sms):
            lost = journal.orders_without(
                task.kind, now - LOST_TASK_WINDOW, now - LOST_TASK_GRACE, with_phone=task is send_order_sms
            )
            for order_id in lost:
                task.delay(order_id)
            requeued += len(lost)
    if requeued:
        logger.warning("Requeued %s lost order tasks", requeued)
    return requeued


@celery_app.task
def reconcile_payments():
    from app.modules.payments.dependencies import payment_service
    from app.tasks.payments import sync_payment
    pending = payment_service().repository.pending()
    for payment in pending:
        sync_payment.delay(payment.id)
    return {"queued": len(pending)}


@celery_app.task
def index_assistant_knowledge():
    from app.modules.assistant.router import assistant_service
    from app.modules.assistant.contracts import ModelUnavailable
    service = assistant_service()
    try:
        return {"indexed": service.repository.index(service.model)}
    except ModelUnavailable:
        logger.info("Assistant index postponed: Ollama is not available")
        return {"postponed": True}
