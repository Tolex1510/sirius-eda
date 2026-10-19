"""
Что происходит после оформления заказа: чек и уведомления клиенту.
OrderService зависит только от абстракции и не знает, выполняется эта работа сразу или в фоне.
"""
from abc import ABC, abstractmethod

from app.domain.entities import User
from app.tasks import stubs


class OrderNotifier(ABC):
    @abstractmethod
    def order_created(self, order_id: int, customer: User) -> None:
        """Вызывается после того, как заказ и списание сохранены в БД."""


class InlineOrderNotifier(OrderNotifier):
    """Всё в потоке запроса: клиент ждёт, пока сгенерируется PDF и уйдут email и SMS."""

    def order_created(self, order_id: int, customer: User) -> None:
        stubs.render_receipt_pdf(order_id)
        stubs.send_email(order_id, customer.email)
        if customer.phone:
            stubs.send_sms(order_id, customer.phone)
