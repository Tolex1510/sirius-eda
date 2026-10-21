"""
Граница модуля доставки со стороны монолита. Роутер зависит только от DeliveryGateway
и не знает, выполняется доставка в этом процессе или в микросервисе.

Две реализации по паттерну Strangler Fig: GrpcDeliveryGateway ходит в новый сервис,
LocalDeliveryGateway выполняет прежний код монолита. Переключение: DELIVERY_BACKEND.
"""
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator

from app.domain.entities import Delivery, DeliveryStatus, User
from app.modules.delivery.service import DeliveryService


class DeliveryUnavailableError(Exception):
    """Сервис доставки не отвечает. Повторить запрос можно позже."""


class DeliveryTimeoutError(DeliveryUnavailableError):
    """Сервис не уложился во время ожидания. Результат действия неизвестен."""


class DeliveryGateway(ABC):
    @abstractmethod
    def assign_courier(self, order_id: int, courier_id: int, actor: User) -> int: ...

    @abstractmethod
    def pick_up(self, delivery_id: int, actor: User) -> Delivery: ...

    @abstractmethod
    def complete_delivery(self, delivery_id: int, actor: User) -> None: ...

    @abstractmethod
    def get_delivery(self, delivery_id: int, actor: User) -> Delivery: ...

    @abstractmethod
    def list_my_deliveries(self, actor: User) -> list[Delivery]: ...

    @abstractmethod
    def track(self, delivery_id: int, actor: User) -> Iterator[Delivery]:
        """Текущее состояние, затем каждое изменение статуса. Заканчивается на завершённой доставке."""


class LocalDeliveryGateway(DeliveryGateway):
    """Прежний путь: бизнес-логика доставки в процессе монолита."""

    POLL_SECONDS = 2.0

    def __init__(self, service: DeliveryService):
        self.service = service

    def assign_courier(self, order_id: int, courier_id: int, actor: User) -> int:
        return self.service.assign_courier(order_id, courier_id, actor=actor)

    def pick_up(self, delivery_id: int, actor: User) -> Delivery:
        return self.service.pick_up(delivery_id, actor=actor)

    def complete_delivery(self, delivery_id: int, actor: User) -> None:
        self.service.complete_delivery(delivery_id, actor=actor)

    def get_delivery(self, delivery_id: int, actor: User) -> Delivery:
        return self.service.get_delivery(delivery_id, actor=actor)

    def list_my_deliveries(self, actor: User) -> list[Delivery]:
        return self.service.list_my_deliveries(actor)

    def track(self, delivery_id: int, actor: User) -> Iterator[Delivery]:
        last_status = None
        while True:
            delivery = self.service.get_delivery(delivery_id, actor=actor)
            if delivery.status != last_status:
                last_status = delivery.status
                yield delivery
            if delivery.status in DeliveryStatus.FINAL:
                return
            time.sleep(self.POLL_SECONDS)
