"""
Consumer модуля заказов: компенсирующий шаг саги. Доставка не удалась,
заказ отменяется, деньги возвращаются, публикуется OrderCancelled.

    python -m app.workers.orders_consumer
"""
from app.core.rabbitmq import ORDERS
from app.dependencies import get_order_notifier, order_repository_scope
from app.domain.events import DeliveryFailed, Receipt
from app.modules.orders.service import OrderService
from app.workers.consumer import EventConsumer, serve

CONSUMER = "orders"


def on_delivery_failed(event: DeliveryFailed, receipt: Receipt) -> str:
    with order_repository_scope() as repository:
        service = OrderService(repository, get_order_notifier())
        cancelled = service.compensate_failed_delivery(event, receipt)
    if cancelled is None:
        return f"order {event.order_id} is not paid, nothing to compensate"
    return f"order {event.order_id} cancelled, refunded {cancelled.refund:.2f} to user {cancelled.customer_id}"


consumer = EventConsumer(CONSUMER, ORDERS, {DeliveryFailed: on_delivery_failed})

if __name__ == "__main__":
    serve(consumer)
