"""
Инфраструктурный слой модуля кухни (круг 3: Interface Adapters).
"""
from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.database import short_transactions
from app.domain.entities import KitchenTicket, KitchenTicketStatus
from app.domain.events import Receipt
from app.domain.exceptions import AlreadyProcessedError
from app.memory_storage import InMemoryStorage
from app.models import KitchenTicket as KitchenTicketModel
from app.outbox import add_receipt, commit_once, has_receipt


class KitchenRepository(ABC):
    """Контракт хранилища, от которого зависит KitchenService."""

    @abstractmethod
    def is_processed(self, receipt: Receipt) -> bool: ...

    @abstractmethod
    def open_ticket(self, order_id: int, receipt: Receipt) -> KitchenTicket | None:
        """
        Ставит заказ в очередь кухни и пишет отметку об обработке одной транзакцией.
        None, если по заказу уже есть запись, например отмена пришла раньше оплаты.
        Повтор отметки: AlreadyProcessedError.
        """

    @abstractmethod
    def cancel_ticket(self, order_id: int, receipt: Receipt) -> bool:
        """
        Снимает заказ с очереди. Если оплата ещё не дошла, оставляет запись cancelled,
        чтобы опоздавший OrderPaid не поставил отменённый заказ в очередь.
        """

    @abstractmethod
    def list_tickets(self, status: str) -> list[KitchenTicket]: ...


@short_transactions
class SqlAlchemyKitchenRepository(KitchenRepository):
    def __init__(self, db: Session):
        self.db = db

    def is_processed(self, receipt: Receipt) -> bool:
        return has_receipt(self.db, receipt)

    def open_ticket(self, order_id: int, receipt: Receipt) -> KitchenTicket | None:
        exists = self.db.query(KitchenTicketModel.id).filter(KitchenTicketModel.order_id == order_id).first()
        add_receipt(self.db, receipt)
        ticket = None
        if not exists:
            ticket = KitchenTicketModel(order_id=order_id, status=KitchenTicketStatus.QUEUED)
            self.db.add(ticket)
        commit_once(self.db)
        return ticket.to_entity() if ticket else None

    def cancel_ticket(self, order_id: int, receipt: Receipt) -> bool:
        ticket = (
            self.db.query(KitchenTicketModel)
            .filter(KitchenTicketModel.order_id == order_id)
            .with_for_update()
            .first()
        )
        add_receipt(self.db, receipt)
        changed = ticket is None or ticket.status == KitchenTicketStatus.QUEUED
        if ticket is None:
            self.db.add(KitchenTicketModel(order_id=order_id, status=KitchenTicketStatus.CANCELLED))
        elif changed:
            ticket.status = KitchenTicketStatus.CANCELLED
            ticket.updated_at = datetime.now(UTC)
        commit_once(self.db)
        return changed

    def list_tickets(self, status: str) -> list[KitchenTicket]:
        rows = (
            self.db.query(KitchenTicketModel)
            .filter(KitchenTicketModel.status == status)
            .order_by(KitchenTicketModel.id)
        )
        return [row.to_entity() for row in rows]


class InMemoryKitchenRepository(KitchenRepository):
    """Хранит данные в памяти процесса. Используется в тестах и без СУБД."""

    def __init__(self, storage: InMemoryStorage):
        self.storage = storage

    def is_processed(self, receipt: Receipt) -> bool:
        return receipt in self.storage.receipts

    def _receive(self, receipt: Receipt) -> None:
        if receipt in self.storage.receipts:
            raise AlreadyProcessedError("Событие уже обработано")
        self.storage.receipts.add(receipt)

    def _find(self, order_id: int) -> KitchenTicket | None:
        return next((t for t in self.storage.kitchen_tickets.values() if t.order_id == order_id), None)

    def open_ticket(self, order_id: int, receipt: Receipt) -> KitchenTicket | None:
        self._receive(receipt)
        if self._find(order_id):
            return None
        return replace(self._add(order_id, KitchenTicketStatus.QUEUED))

    def cancel_ticket(self, order_id: int, receipt: Receipt) -> bool:
        self._receive(receipt)
        ticket = self._find(order_id)
        if ticket is None:
            self._add(order_id, KitchenTicketStatus.CANCELLED)
            return True
        if ticket.status != KitchenTicketStatus.QUEUED:
            return False
        ticket.status = KitchenTicketStatus.CANCELLED
        return True

    def list_tickets(self, status: str) -> list[KitchenTicket]:
        return [replace(t) for t in self.storage.kitchen_tickets.values() if t.status == status]

    def _add(self, order_id: int, status: str) -> KitchenTicket:
        ticket_id = self.storage.next_id("kitchen_tickets")
        ticket = KitchenTicket(id=ticket_id, order_id=order_id, status=status, created_at=datetime.now(UTC))
        self.storage.kitchen_tickets[ticket_id] = ticket
        return ticket
