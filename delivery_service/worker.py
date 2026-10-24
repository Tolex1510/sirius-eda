"""
Consumer микросервиса доставки: на оплаченный заказ назначает свободного курьера.
Свободных нет: событие DeliveryFailed, заказ отменит модуль заказов.

    python -m delivery_service.worker
"""
from app.core.rabbitmq import DELIVERY
from app.domain.entities import Delivery
from app.domain.events import OrderPaid, Receipt
from app.modules.delivery.service import DeliveryService
from app.workers.consumer import EventConsumer, serve
from delivery_service.server import sql_repository

CONSUMER = "delivery"


def on_order_paid(event: OrderPaid, receipt: Receipt) -> str:
    with sql_repository() as repository:
        result = DeliveryService(repository).dispatch(event, receipt)
    if isinstance(result, Delivery):
        return f"order {event.order_id}: delivery {result.id}, courier {result.courier_id}"
    if result is None:
        return f"order {event.order_id}: delivery not needed"
    return f"order {event.order_id}: {result.reason}, DeliveryFailed published"


consumer = EventConsumer(CONSUMER, DELIVERY, {OrderPaid: on_order_paid})

if __name__ == "__main__":
    serve(consumer)
