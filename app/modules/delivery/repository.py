"""
Инфраструктурный слой модуля доставки (круг 3: Interface Adapters).
"""
from abc import ABC, abstractmethod
from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import short_transactions
from app.domain.entities import Delivery, DeliveryStatus, Order, Role, User
from app.domain.events import DeliveryFailed, Receipt
from app.domain.exceptions import AlreadyProcessedError
from app.memory_storage import InMemoryStorage
from app.models import Delivery as DeliveryModel
from app.models import Order as OrderModel
from app.models import Role as RoleModel
from app.models import User as UserModel
from app.outbox import add_receipt, add_to_outbox, commit_once, has_receipt


class DeliveryRepository(ABC):
    """Контракт хранилища, от которого зависит DeliveryService."""

    @abstractmethod
    def get_order_by_id(self, order_id: int) -> Order | None: ...

    @abstractmethod
    def get_courier_by_id(self, courier_id: int) -> User | None: ...

    @abstractmethod
    def get_active_delivery_by_courier(self, courier_id: int) -> Delivery | None: ...

    @abstractmethod
    def get_by_id(self, delivery_id: int) -> Delivery | None: ...

    @abstractmethod
    def list_by_courier(self, courier_id: int) -> list[Delivery]: ...

    @abstractmethod
    def list_by_customer(self, user_id: int) -> list[Delivery]:
        """Доставки заказов, оформленных пользователем."""

    @abstractmethod
    def create(self, order_id: int, courier_id: int, status: str) -> int:
        """Создаёт доставку и возвращает её идентификатор."""

    @abstractmethod
    def save_status(self, delivery: Delivery) -> None: ...

    @abstractmethod
    def save_completion(self, delivery: Delivery, order: Order | None) -> None:
        """Сохраняет новые статусы доставки и заказа одной транзакцией."""

    @abstractmethod
    def get_by_order(self, order_id: int) -> Delivery | None:
        """Неотменённая доставка заказа."""

    @abstractmethod
    def is_processed(self, receipt: Receipt) -> bool: ...

    @abstractmethod
    def assign_free_courier(self, order_id: int, receipt: Receipt) -> Delivery | None:
        """
        Находит свободного курьера, создаёт доставку и пишет отметку об обработке одной транзакцией.
        None, если свободных курьеров нет: тогда не пишется ничего. Повтор отметки: AlreadyProcessedError.
        """

    @abstractmethod
    def record_failure(self, event: DeliveryFailed, receipt: Receipt) -> None:
        """Событие о провале в outbox и отметка об обработке одной транзакцией."""


@short_transactions
class SqlAlchemyDeliveryRepository(DeliveryRepository):
    def __init__(self, db: Session):
        self.db = db

    def get_order_by_id(self, order_id: int) -> Order | None:
        order = self.db.query(OrderModel).filter(OrderModel.id == order_id).first()
        return order.to_entity() if order else None

    def get_courier_by_id(self, courier_id: int) -> User | None:
        courier = self.db.query(UserModel).filter(UserModel.id == courier_id).first()
        return courier.to_entity() if courier else None

    def get_active_delivery_by_courier(self, courier_id: int) -> Delivery | None:
        active = self.db.query(DeliveryModel).filter(
            DeliveryModel.courier_id == courier_id,
            DeliveryModel.status.in_(DeliveryStatus.ACTIVE),
        ).first()
        return active.to_entity() if active else None

    def get_by_id(self, delivery_id: int) -> Delivery | None:
        delivery = self.db.query(DeliveryModel).filter(DeliveryModel.id == delivery_id).first()
        return delivery.to_entity() if delivery else None

    def list_by_courier(self, courier_id: int) -> list[Delivery]:
        rows = self.db.query(DeliveryModel).filter(DeliveryModel.courier_id == courier_id).order_by(DeliveryModel.id)
        return [row.to_entity() for row in rows]

    def list_by_customer(self, user_id: int) -> list[Delivery]:
        rows = (
            self.db.query(DeliveryModel)
            .join(OrderModel, OrderModel.id == DeliveryModel.order_id)
            .filter(OrderModel.user_id == user_id)
            .order_by(DeliveryModel.id)
        )
        return [row.to_entity() for row in rows]

    def create(self, order_id: int, courier_id: int, status: str) -> int:
        new_delivery = DeliveryModel(order_id=order_id, courier_id=courier_id, status=status)
        self.db.add(new_delivery)
        self.db.commit()
        self.db.refresh(new_delivery)
        return new_delivery.id

    def save_status(self, delivery: Delivery) -> None:
        self.db.query(DeliveryModel).filter(DeliveryModel.id == delivery.id).update({"status": delivery.status})
        self.db.commit()

    def save_completion(self, delivery: Delivery, order: Order | None) -> None:
        row = self.db.query(DeliveryModel).filter(DeliveryModel.id == delivery.id).one()
        row.status = delivery.status
        if order:
            order_row = self.db.query(OrderModel).filter(OrderModel.id == order.id).one()
            order_row.status = order.status
        self.db.commit()

    def get_by_order(self, order_id: int) -> Delivery | None:
        row = self.db.query(DeliveryModel).filter(
            DeliveryModel.order_id == order_id,
            DeliveryModel.status != DeliveryStatus.CANCELLED,
        ).first()
        return row.to_entity() if row else None

    def is_processed(self, receipt: Receipt) -> bool:
        return has_receipt(self.db, receipt)

    def assign_free_courier(self, order_id: int, receipt: Receipt) -> Delivery | None:
        busy = select(DeliveryModel.courier_id).where(
            DeliveryModel.status.in_(DeliveryStatus.ACTIVE),
            DeliveryModel.courier_id.is_not(None),
        )
        # SKIP LOCKED: два заказа, оплаченные одновременно, не получат одного курьера,
        # второй возьмёт следующего свободного.
        courier = (
            self.db.query(UserModel)
            .join(RoleModel, RoleModel.id == UserModel.role_id)
            .filter(RoleModel.name == Role.COURIER, UserModel.is_blocked.is_(False), UserModel.id.not_in(busy))
            .order_by(UserModel.id)
            .with_for_update(of=UserModel, skip_locked=True)
            .first()
        )
        if not courier:
            return None
        delivery = DeliveryModel(order_id=order_id, courier_id=courier.id, status=DeliveryStatus.IN_PROGRESS)
        self.db.add(delivery)
        add_receipt(self.db, receipt)
        commit_once(self.db)
        return delivery.to_entity()

    def record_failure(self, event: DeliveryFailed, receipt: Receipt) -> None:
        add_to_outbox(self.db, event)
        add_receipt(self.db, receipt)
        commit_once(self.db)


class InMemoryDeliveryRepository(DeliveryRepository):
    """Хранит данные в памяти процесса. Используется в тестах и без СУБД."""

    def __init__(self, storage: InMemoryStorage):
        self.storage = storage

    def get_order_by_id(self, order_id: int) -> Order | None:
        order = self.storage.orders.get(order_id)
        return replace(order) if order else None

    def get_courier_by_id(self, courier_id: int) -> User | None:
        courier = self.storage.users.get(courier_id)
        return replace(courier) if courier else None

    def get_active_delivery_by_courier(self, courier_id: int) -> Delivery | None:
        for delivery in self.storage.deliveries.values():
            if delivery.courier_id == courier_id and delivery.status in DeliveryStatus.ACTIVE:
                return replace(delivery)
        return None

    def get_by_id(self, delivery_id: int) -> Delivery | None:
        delivery = self.storage.deliveries.get(delivery_id)
        return replace(delivery) if delivery else None

    def list_by_courier(self, courier_id: int) -> list[Delivery]:
        return [replace(d) for d in self.storage.deliveries.values() if d.courier_id == courier_id]

    def list_by_customer(self, user_id: int) -> list[Delivery]:
        return [
            replace(d)
            for d in self.storage.deliveries.values()
            if self.storage.orders[d.order_id].user_id == user_id
        ]

    def create(self, order_id: int, courier_id: int, status: str) -> int:
        delivery_id = self.storage.next_id("deliveries")
        self.storage.deliveries[delivery_id] = Delivery(
            id=delivery_id,
            order_id=order_id,
            courier_id=courier_id,
            status=status,
        )
        return delivery_id

    def save_status(self, delivery: Delivery) -> None:
        self.storage.deliveries[delivery.id].status = delivery.status

    def save_completion(self, delivery: Delivery, order: Order | None) -> None:
        self.storage.deliveries[delivery.id] = replace(delivery)
        if order:
            self.storage.orders[order.id] = replace(order)

    def get_by_order(self, order_id: int) -> Delivery | None:
        for delivery in self.storage.deliveries.values():
            if delivery.order_id == order_id and delivery.status != DeliveryStatus.CANCELLED:
                return replace(delivery)
        return None

    def is_processed(self, receipt: Receipt) -> bool:
        return receipt in self.storage.receipts

    def _receive(self, receipt: Receipt) -> None:
        if receipt in self.storage.receipts:
            raise AlreadyProcessedError("Событие уже обработано")
        self.storage.receipts.add(receipt)

    def assign_free_courier(self, order_id: int, receipt: Receipt) -> Delivery | None:
        busy = {d.courier_id for d in self.storage.deliveries.values() if d.status in DeliveryStatus.ACTIVE}
        free = sorted(
            u.id for u in self.storage.users.values()
            if u.role == Role.COURIER and not u.is_blocked and u.id not in busy
        )
        if not free:
            return None
        self._receive(receipt)
        delivery_id = self.create(order_id, free[0], DeliveryStatus.IN_PROGRESS)
        return replace(self.storage.deliveries[delivery_id])

    def record_failure(self, event: DeliveryFailed, receipt: Receipt) -> None:
        self._receive(receipt)
        self.storage.outbox.append(event)
