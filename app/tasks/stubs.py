"""
Заглушки внешних сервисов: генератор PDF, почтовый и SMS-шлюз.
Задержки имитируют сетевые вызовы к провайдерам, сбои имитируют их недоступность.
"""
import logging
import time

from app.core.config import settings

logger = logging.getLogger(__name__)


class ExternalServiceError(Exception):
    """Провайдер временно недоступен. Такой вызов имеет смысл повторить."""


def render_receipt_pdf(order_id: int) -> None:
    time.sleep(2)
    logger.info("Receipt PDF rendered for order %s", order_id)


def send_email(order_id: int, address: str) -> None:
    time.sleep(1)
    # Как в методичке: почта лежит для каждого N-го заказа, ретраи не помогают, задача уходит в DLQ.
    if settings.FAKE_EMAIL_FAIL_EVERY and order_id % settings.FAKE_EMAIL_FAIL_EVERY == 0:
        raise ExternalServiceError("Email service unavailable")
    logger.info("Order %s email sent", order_id)


def send_sms(order_id: int, phone: str, attempt: int = 0) -> None:
    time.sleep(1)
    # Шлюз не отвечает на первую попытку для каждого N-го заказа: здесь ретрай спасает.
    if settings.FAKE_SMS_FLAKY_EVERY and order_id % settings.FAKE_SMS_FLAKY_EVERY == 0 and attempt == 0:
        raise ExternalServiceError("SMS gateway timeout")
    logger.info("Order %s SMS sent", order_id)
