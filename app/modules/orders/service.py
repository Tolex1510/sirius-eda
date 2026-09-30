"""
Слой бизнес-логики модуля заказов (круги 1 и 2: Entities и Use Cases).
Импорты fastapi и sqlalchemy здесь запрещены.
"""
from app.domain.entities import Order, OrderStatus, Role, User
from app.domain.exceptions import AccessDeniedError, BusinessRuleError, NotFoundError
from app.modules.orders.repository import OrderRepository

KITCHEN_STATUSES = (OrderStatus.PROCESSING, OrderStatus.PAID)


class OrderService:
    def __init__(self, repository: OrderRepository):
        self.repository = repository

    def create_order(self, user_id: int, item_id: int, quantity: int) -> int:
        """Сценарий оформления заказа. Возвращает идентификатор заказа."""
        user = self.repository.get_user_by_id(user_id)
        if not user:
            raise NotFoundError("Пользователь не найден")

        item = self.repository.get_menu_item_by_id(item_id)
        if not item:
            raise NotFoundError("Блюдо не найдено")

        if not item.is_available:
            raise BusinessRuleError("Блюдо недоступно")

        total_cost = item.price * quantity
        if user.balance < total_cost:
            raise BusinessRuleError("Недостаточно средств на балансе студента")

        return self.repository.save_order(
            user_id=user_id,
            item_id=item_id,
            quantity=quantity,
            total_cost=total_cost,
            new_balance=user.balance - total_cost,
        )

    def cancel_order(self, order_id: int, actor: User) -> Order:
        """Отменяет заказ и возвращает деньги. Отменить можно только свой заказ."""
        order = self.repository.get_order(order_id)
        if not order:
            raise NotFoundError("Заказ не найден")

        # Защита от IDOR: order_id пришёл от клиента, владельца сверяем с пользователем из JWT.
        if order.user_id != actor.id and actor.role != Role.ADMIN:
            raise AccessDeniedError("Нет доступа к чужому заказу")

        if order.status != OrderStatus.PROCESSING or not self.repository.cancel_and_refund(order):
            raise BusinessRuleError("Отменить можно только заказ в обработке")

        order.status = OrderStatus.CANCELLED
        return order

    def list_user_orders(self, actor: User) -> list[Order]:
        return self.repository.list_orders_by_user(actor.id)

    def get_kitchen_orders(self) -> list[Order]:
        return self.repository.list_orders_by_status(KITCHEN_STATUSES)
