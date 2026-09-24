"""
Инфраструктурный слой модуля доставки (круг 3: Interface Adapters).
"""
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.domain.entities import Delivery, DeliveryStatus, Order, User
from app.models import Delivery as DeliveryModel
from app.models import Order as OrderModel
from app.models import User as UserModel


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
    def create(self, order_id: int, courier_id: int, status: str) -> int:
        """Создаёт доставку и возвращает её идентификатор."""

    @abstractmethod
    def save_completion(self, delivery: Delivery, order: Order | None) -> None:
        """Сохраняет новые статусы доставки и заказа одной транзакцией."""


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
            DeliveryModel.status == DeliveryStatus.IN_PROGRESS,
        ).first()
        return active.to_entity() if active else None

    def get_by_id(self, delivery_id: int) -> Delivery | None:
        delivery = self.db.query(DeliveryModel).filter(DeliveryModel.id == delivery_id).first()
        return delivery.to_entity() if delivery else None

    def create(self, order_id: int, courier_id: int, status: str) -> int:
        new_delivery = DeliveryModel(order_id=order_id, courier_id=courier_id, status=status)
        self.db.add(new_delivery)
        self.db.commit()
        self.db.refresh(new_delivery)
        return new_delivery.id

    def save_completion(self, delivery: Delivery, order: Order | None) -> None:
        row = self.db.query(DeliveryModel).filter(DeliveryModel.id == delivery.id).one()
        row.status = delivery.status
        if order:
            order_row = self.db.query(OrderModel).filter(OrderModel.id == order.id).one()
            order_row.status = order.status
        self.db.commit()
