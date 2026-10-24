"""
Слой бизнес-логики модуля доставки (круги 1 и 2: Entities и Use Cases).
Импорты fastapi и sqlalchemy здесь запрещены.
"""
from app.domain.entities import Delivery, DeliveryStatus, OrderStatus, Role, User
from app.domain.events import DeliveryFailed, OrderPaid, Receipt
from app.domain.exceptions import AccessDeniedError, AlreadyProcessedError, BusinessRuleError, NotFoundError
from app.modules.delivery.repository import DeliveryRepository


class DeliveryService:
    def __init__(self, repository: DeliveryRepository):
        self.repository = repository

    def assign_courier(self, order_id: int, courier_id: int, actor: User) -> int:
        """Назначает курьера на заказ и возвращает идентификатор доставки."""
        # courier_id пришёл от клиента: курьер может взять доставку только на себя.
        if actor.role != Role.ADMIN and courier_id != actor.id:
            raise AccessDeniedError("Курьер может назначить доставку только себе")

        order = self.repository.get_order_by_id(order_id)
        if not order:
            raise NotFoundError("Заказ не найден")

        if order.status != OrderStatus.PAID:
            raise BusinessRuleError("Курьера можно назначить только на оплаченный заказ")

        courier = self.repository.get_courier_by_id(courier_id)
        if not courier:
            raise NotFoundError("Курьер не найден")

        if courier.is_blocked:
            raise AccessDeniedError("Курьер заблокирован и не может быть назначен")

        if courier.role != Role.COURIER:
            raise BusinessRuleError("Назначить можно только пользователя с ролью courier")

        if self.repository.get_active_delivery_by_courier(courier_id):
            raise BusinessRuleError("У курьера уже есть активная доставка")

        if self.repository.get_by_order(order_id):
            raise BusinessRuleError("У заказа уже есть доставка")

        return self.repository.create(
            order_id=order_id,
            courier_id=courier_id,
            status=DeliveryStatus.IN_PROGRESS,
        )

    def dispatch(self, event: OrderPaid, receipt: Receipt) -> Delivery | DeliveryFailed | None:
        """
        Реакция на оплату: назначает свободного курьера. Свободных нет: шаг саги, событие DeliveryFailed,
        по которому модуль заказов отменит заказ и вернёт деньги.
        None, если доставка не нужна: заказ уже отменён или курьер назначен вручную.
        """
        if self.repository.is_processed(receipt):
            raise AlreadyProcessedError("Событие уже обработано")

        order = self.repository.get_order_by_id(event.order_id)
        if not order or order.status != OrderStatus.PAID or self.repository.get_by_order(order.id):
            return None

        delivery = self.repository.assign_free_courier(order.id, receipt)
        if delivery:
            return delivery

        failed = DeliveryFailed(order_id=order.id, reason="Нет свободного курьера")
        self.repository.record_failure(failed, receipt)
        return failed

    def get_delivery(self, delivery_id: int, actor: User) -> Delivery:
        delivery = self.repository.get_by_id(delivery_id)
        if not delivery:
            raise NotFoundError("Доставка не найдена")
        self._ensure_can_view(delivery, actor)
        return delivery

    def list_my_deliveries(self, actor: User) -> list[Delivery]:
        if actor.role == Role.COURIER:
            return self.repository.list_by_courier(actor.id)
        return self.repository.list_by_customer(actor.id)

    def pick_up(self, delivery_id: int, actor: User) -> Delivery:
        """Курьер забрал заказ на кухне и везёт его."""
        delivery = self.repository.get_by_id(delivery_id)
        if not delivery:
            raise NotFoundError("Доставка не найдена")

        if actor.role != Role.ADMIN and delivery.courier_id != actor.id:
            raise AccessDeniedError("Забрать можно только свой заказ")

        if delivery.status != DeliveryStatus.IN_PROGRESS:
            raise BusinessRuleError("Забрать можно только заказ, на который курьер назначен")

        delivery.status = DeliveryStatus.ON_THE_WAY
        self.repository.save_status(delivery)
        return delivery

    def complete_delivery(self, delivery_id: int, actor: User) -> None:
        delivery = self.repository.get_by_id(delivery_id)
        if not delivery:
            raise NotFoundError("Доставка не найдена")

        if actor.role != Role.ADMIN and delivery.courier_id != actor.id:
            raise AccessDeniedError("Завершить можно только свою доставку")

        if delivery.status == DeliveryStatus.COMPLETED:
            raise BusinessRuleError("Доставка уже завершена")

        if delivery.status == DeliveryStatus.CANCELLED:
            raise BusinessRuleError("Отменённую доставку нельзя завершить")

        delivery.status = DeliveryStatus.COMPLETED

        order = self.repository.get_order_by_id(delivery.order_id)
        if order:
            order.status = OrderStatus.DELIVERED

        self.repository.save_completion(delivery, order)

    def _ensure_can_view(self, delivery: Delivery, actor: User) -> None:
        """Защита от IDOR: доставку видят её курьер, заказчик и администратор."""
        if actor.role == Role.ADMIN or delivery.courier_id == actor.id:
            return
        order = self.repository.get_order_by_id(delivery.order_id)
        if order and order.user_id == actor.id:
            return
        raise AccessDeniedError("Нет доступа к чужой доставке")
