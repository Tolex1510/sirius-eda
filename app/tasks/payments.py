"""Повторная проверка: 1, 2, 4, 8 секунд + jitter, затем DLQ и ручная сверка."""
import random
from celery import Task
from app.core.celery_app import celery_app
from app.modules.payments.contracts import GatewayUnavailable
from app.modules.payments.dependencies import payment_service
from app.tasks.dead_letters import send_to_dead_letters


class PaymentSyncTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        payment_id = args[0] if args else kwargs['payment_id']
        from app.database import SessionLocal
        from app.modules.payments.repository import SqlPaymentRepository
        SqlPaymentRepository(SessionLocal).mark_review(payment_id)
        send_to_dead_letters(self.name, task_id, args, kwargs, 'Не удалось подтвердить состояние у провайдера')


@celery_app.task(base=PaymentSyncTask, bind=True, max_retries=4)
def sync_payment(self, payment_id):
    service = payment_service()
    try:
        result = service.sync(service.repository.get(payment_id))
        return {'status': result.status, 'refund_status': result.refund_status}
    except GatewayUnavailable as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries + random.uniform(0, .5))
