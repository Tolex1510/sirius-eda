"""
Слой бизнес-логики кухни (круги 1 и 2: Entities и Use Cases).
Кухня узнаёт о заказах из событий и не вызывает модуль заказов.
"""
from app.domain.entities import KitchenTicket, KitchenTicketStatus
from app.domain.events import OrderCancelled, OrderPaid, Receipt
from app.domain.exceptions import AlreadyProcessedError
from app.modules.kitchen.repository import KitchenRepository


class KitchenService:
    def __init__(self, repository: KitchenRepository):
        self.repository = repository

    def accept(self, event: OrderPaid, receipt: Receipt) -> KitchenTicket | None:
        """Оплаченный заказ встаёт в очередь кухни. None, если запись по заказу уже есть, например отмена."""
        self._ensure_new(receipt)
        return self.repository.open_ticket(event.order_id, receipt)

    def cancel(self, event: OrderCancelled, receipt: Receipt) -> bool:
        """Отменённый заказ снимается с очереди, чтобы его не готовили."""
        self._ensure_new(receipt)
        return self.repository.cancel_ticket(event.order_id, receipt)

    def queue(self) -> list[KitchenTicket]:
        return self.repository.list_tickets(KitchenTicketStatus.QUEUED)

    def _ensure_new(self, receipt: Receipt) -> None:
        if self.repository.is_processed(receipt):
            raise AlreadyProcessedError("Событие уже обработано")
