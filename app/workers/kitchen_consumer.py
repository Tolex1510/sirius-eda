"""
Consumer кухни: оплаченный заказ встаёт в очередь, отменённый снимается.

    python -m app.workers.kitchen_consumer
"""
from app.core.rabbitmq import KITCHEN
from app.dependencies import kitchen_repository_scope
from app.domain.events import OrderCancelled, OrderPaid, Receipt
from app.modules.kitchen.service import KitchenService
from app.workers.consumer import EventConsumer, serve

CONSUMER = "kitchen"


def on_order_paid(event: OrderPaid, receipt: Receipt) -> str:
    with kitchen_repository_scope() as repository:
        ticket = KitchenService(repository).accept(event, receipt)
    if ticket is None:
        return f"order {event.order_id} already known to kitchen, not queued again"
    return f"order {event.order_id} queued as ticket {ticket.id}"


def on_order_cancelled(event: OrderCancelled, receipt: Receipt) -> str:
    with kitchen_repository_scope() as repository:
        changed = KitchenService(repository).cancel(event, receipt)
    return f"order {event.order_id} {'removed from queue' if changed else 'was not queued'}"


consumer = EventConsumer(CONSUMER, KITCHEN, {OrderPaid: on_order_paid, OrderCancelled: on_order_cancelled})

if __name__ == "__main__":
    serve(consumer)
