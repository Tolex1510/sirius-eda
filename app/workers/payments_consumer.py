"""Компенсирующий шаг саги: OrderCancelled → намерение refund → worker.

    python -m app.workers.payments_consumer
"""
from app.core.rabbitmq import PAYMENTS
from app.domain.events import OrderCancelled, Receipt
from app.modules.payments.dependencies import payment_service
from app.tasks.payments import sync_payment
from app.workers.consumer import EventConsumer, serve

CONSUMER = 'payments'


def on_order_cancelled(event: OrderCancelled, receipt: Receipt) -> str:
    payment = payment_service().on_order_cancelled(event, receipt)
    if payment is None:
        return f'order {event.order_id}: refund not needed or already requested'
    # Намерение уже в БД. Если Redis недоступен, Beat повторно найдёт его после восстановления.
    sync_payment.delay(payment.id)
    return f'order {event.order_id}: gateway refund requested'


consumer = EventConsumer(CONSUMER, PAYMENTS, {OrderCancelled: on_order_cancelled})

if __name__ == '__main__':
    serve(consumer)
