"""
Что происходит после оформления заказа: чек и уведомления клиенту.
OrderService зависит только от абстракции и не знает, выполняется эта работа сразу или в фоне.
"""
import logging
from abc import ABC, abstractmethod

from kombu.exceptions import OperationalError

from app.domain.entities import User
from app.tasks import stubs
from app.tasks.orders import generate_order_pdf, send_order_email, send_order_sms

logger = logging.getLogger(__name__)


class OrderNotifier(ABC):
    @abstractmethod
    def order_created(self, order_id: int, customer: User) -> None:
        """Вызывается после того, как заказ и списание сохранены в БД."""


class CeleryOrderNotifier(OrderNotifier):
    """Ставит задачи в очередь и сразу возвращает управление: клиент не ждёт PDF, email и SMS."""

    def order_created(self, order_id: int, customer: User) -> None:
        tasks = [generate_order_pdf, send_order_email]
        if customer.phone:
            tasks.append(send_order_sms)
        try:
            for task in tasks:
                task.delay(order_id)
        except OperationalError:
            # Заказ и списание уже в БД, откатывать их из-за уведомлений нельзя.
            logger.error("Order %s: broker unavailable, background tasks not queued", order_id, exc_info=True)


class InlineOrderNotifier(OrderNotifier):
    """Всё в потоке запроса, как до Celery: клиент ждёт PDF, email и SMS. Ретраев нет."""

    def order_created(self, order_id: int, customer: User) -> None:
        try:
            stubs.render_receipt_pdf(order_id)
            stubs.send_email(order_id, customer.email)
            if customer.phone:
                stubs.send_sms(order_id, customer.phone)
        except stubs.ExternalServiceError:
            logger.warning("Order %s: notification failed", order_id, exc_info=True)
