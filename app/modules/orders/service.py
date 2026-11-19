"""
Слой бизнес-логики модуля заказов (круги 1 и 2: Entities и Use Cases).
Импорты fastapi и sqlalchemy здесь запрещены.
"""
from datetime import date, timedelta

from app.domain.entities import DailyOrderStats, Order, OrderStatus, Role, User
from app.domain.events import DeliveryFailed, OrderCancelled, OrderPaid, Receipt
from app.domain.exceptions import AccessDeniedError, AlreadyProcessedError, BusinessRuleError, NotFoundError
from app.modules.orders.notifier import OrderNotifier
from app.modules.orders.repository import OrderRepository
from app.core.observability import orders_created, start_span

KITCHEN_STATUSES = (OrderStatus.PROCESSING, OrderStatus.PAID)


class OrderService:
    def __init__(self, repository: OrderRepository, notifier: OrderNotifier):
        self.repository = repository
        self.notifier = notifier

    def create_order(
        self, user_id: int, item_id: int, quantity: int, correlation_id: str | None = None,
    ) -> int:
        with start_span("orders.create") as span:
            span.set_attribute("app.user_id", user_id)
            span.set_attribute("app.item_id", item_id)
            if correlation_id:
                span.set_attribute("app.correlation_id", correlation_id)
            return self._create_order(user_id, item_id, quantity, correlation_id)

    def _create_order(self, user_id: int, item_id: int, quantity: int, correlation_id: str | None) -> int:
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

        save_order_args = dict(
            user_id=user_id,
            item_id=item_id,
            quantity=quantity,
            total_cost=total_cost,
            new_balance=user.balance - total_cost,
        )
        if correlation_id is not None:
            save_order_args["correlation_id"] = correlation_id
        order_id = self.repository.save_order(**save_order_args)
        orders_created.inc()
        import structlog

        structlog.get_logger(__name__).info(
            "order_created", order_id=order_id, user_id=user_id, correlation_id=correlation_id,
        )
        # После сохранения: чек и уведомления о заказе, которого нет в БД, никому не нужны.
        self.notifier.order_created(order_id, user)
        return order_id

    def cancel_order(self, order_id: int, actor: User) -> Order:
        """Отменяет заказ и возвращает деньги. Отменить можно только свой заказ."""
        order = self.repository.get_order(order_id)
        if not order:
            raise NotFoundError("Заказ не найден")

        # Защита от IDOR: order_id пришёл от клиента, владельца сверяем с пользователем из JWT.
        if order.user_id != actor.id and actor.role != Role.ADMIN:
            raise AccessDeniedError("Нет доступа к чужому заказу")

        if order.payment_source != "internal_balance":
            raise BusinessRuleError("Используйте отмену внешнего заказа")

        if order.status != OrderStatus.PROCESSING or not self.repository.cancel_and_refund(order):
            raise BusinessRuleError("Отменить можно только заказ в обработке")

        order.status = OrderStatus.CANCELLED
        return order

    def pay_order(self, order_id: int, actor: User) -> Order:
        """
        Подтверждает оплату: деньги списаны при оформлении, здесь заказ переходит в paid.
        Кухня и доставка узнают об этом из события OrderPaid, сервис о них не знает.
        """
        order = self.repository.get_order(order_id)
        if not order:
            raise NotFoundError("Заказ не найден")

        if order.user_id != actor.id and actor.role != Role.ADMIN:
            raise AccessDeniedError("Нет доступа к чужому заказу")

        if order.payment_source != "internal_balance":
            raise BusinessRuleError("Внешнюю оплату подтверждает платёжный провайдер")

        event = OrderPaid(
            order_id=order.id, customer_id=order.user_id, amount=order.total_cost,
            correlation_id=order.correlation_id,
        )
        # Статус и событие сохраняются одной транзакцией: оплаченный заказ без события невозможен.
        if order.status != OrderStatus.PROCESSING or not self.repository.mark_paid(order, event):
            raise BusinessRuleError("Оплатить можно только заказ в обработке")

        order.status = OrderStatus.PAID
        return order

    def compensate_failed_delivery(self, event: DeliveryFailed, receipt: Receipt) -> OrderCancelled | None:
        """
        Компенсирующий шаг саги: доставку создать не удалось, заказ отменяется, деньги возвращаются.
        None, если отменять нечего: заказ уже отменён или не оплачен.
        """
        if self.repository.is_processed(receipt):
            raise AlreadyProcessedError("Событие уже обработано")

        order = self.repository.get_order(event.order_id)
        if not order or order.status != OrderStatus.PAID:
            return None

        cancelled = OrderCancelled(
            order_id=order.id, customer_id=order.user_id, refund=order.total_cost, reason=event.reason,
            correlation_id=event.correlation_id,
        )
        return cancelled if self.repository.cancel_paid_and_refund(order, cancelled, receipt) else None

    def list_user_orders(self, actor: User) -> list[Order]:
        return self.repository.list_orders_by_user(actor.id)

    def get_kitchen_orders(self) -> list[Order]:
        return self.repository.list_orders_by_status(KITCHEN_STATUSES)


class OrderStatsService:
    """Сводка заказов по дням. Пересчёт запускает Celery Beat, чтение доступно администратору."""

    def __init__(self, repository: OrderRepository):
        self.repository = repository

    def refresh(self, today: date) -> list[DailyOrderStats]:
        # Вчерашний день тоже: заказ, отменённый после полуночи, меняет вчерашнюю сводку.
        return [self.repository.refresh_daily_stats(day) for day in (today - timedelta(days=1), today)]

    def recent(self, days: int) -> list[DailyOrderStats]:
        return self.repository.list_daily_stats(days)
