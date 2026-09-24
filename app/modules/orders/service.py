"""
Слой бизнес-логики модуля заказов (круги 1 и 2: Entities и Use Cases).
Импорты fastapi и sqlalchemy здесь запрещены.
"""
from app.domain.exceptions import BusinessRuleError, NotFoundError
from app.modules.orders.repository import OrderRepository


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
            new_balance=user.balance - total_cost,
        )
