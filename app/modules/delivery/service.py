"""
Слой бизнес-логики модуля доставки (круги 1 и 2: Entities и Use Cases).
Импорты fastapi и sqlalchemy здесь запрещены.
"""
from app.domain.entities import DeliveryStatus, OrderStatus
from app.domain.exceptions import AccessDeniedError, BusinessRuleError, NotFoundError
from app.modules.delivery.repository import DeliveryRepository


class DeliveryService:
    def __init__(self, repository: DeliveryRepository):
        self.repository = repository

    def assign_courier(self, order_id: int, courier_id: int) -> int:
        """Назначает курьера на заказ и возвращает идентификатор доставки."""
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

        if self.repository.get_active_delivery_by_courier(courier_id):
            raise BusinessRuleError("У курьера уже есть активная доставка")

        return self.repository.create(
            order_id=order_id,
            courier_id=courier_id,
            status=DeliveryStatus.IN_PROGRESS,
        )

    def complete_delivery(self, delivery_id: int) -> None:
        delivery = self.repository.get_by_id(delivery_id)
        if not delivery:
            raise NotFoundError("Доставка не найдена")

        if delivery.status == DeliveryStatus.COMPLETED:
            raise BusinessRuleError("Доставка уже завершена")

        if delivery.status == DeliveryStatus.CANCELLED:
            raise BusinessRuleError("Отменённую доставку нельзя завершить")

        delivery.status = DeliveryStatus.COMPLETED

        order = self.repository.get_order_by_id(delivery.order_id)
        if order:
            order.status = OrderStatus.DELIVERED

        self.repository.save_completion(delivery, order)
