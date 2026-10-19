"""
Заглушки внешних сервисов: генератор PDF, почтовый и SMS-шлюз.
Задержки имитируют сетевые вызовы к провайдерам.
"""
import logging
import time

logger = logging.getLogger(__name__)


def render_receipt_pdf(order_id: int) -> None:
    time.sleep(2)
    logger.info("Receipt PDF rendered for order %s", order_id)


def send_email(order_id: int, address: str) -> None:
    time.sleep(1)
    logger.info("Order %s email sent", order_id)


def send_sms(order_id: int, phone: str) -> None:
    time.sleep(1)
    logger.info("Order %s SMS sent", order_id)
