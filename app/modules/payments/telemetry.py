"""Структурированный журнал webhook без тела запроса и секретов."""
from datetime import UTC, datetime
import json
import logging
import sys

logger = logging.getLogger('sirius.payments.webhook')
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def record_webhook(event, object_id, payment, http_status, elapsed):
    logger.info(json.dumps({
        'timestamp': datetime.now(UTC).isoformat(),
        'kind': 'payment_webhook',
        'event': event,
        'object_id': object_id,
        'order_id': payment.order_id if payment else None,
        'payment_status': payment.status if payment else None,
        'refund_status': payment.refund_status if payment else None,
        'result': 'failed' if http_status >= 400 else ('processed' if payment else 'ignored'),
        'http_status': http_status,
        'duration_ms': round(elapsed * 1000, 2),
    }, ensure_ascii=False))
