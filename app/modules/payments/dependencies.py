from app.core.config import settings
from app.database import SessionLocal
from app.modules.payments.contracts import GatewayResult, PaymentGateway
from app.modules.payments.gateway import YooKassaGateway
from app.modules.payments.repository import SqlPaymentRepository
from app.modules.payments.service import PaymentService


class DemoGateway(PaymentGateway):
    """Автономный симулятор, состояние хранится в PostgreSQL и переживает перезапуск."""
    name = 'demo'

    def __init__(self, repository):
        self.repository = repository

    def create(self, payment):
        return GatewayResult(payment.id, 'pending', payment.amount, 'RUB', payment.order_id,
                             f'/payment/demo/{payment.id}')

    def fetch(self, gateway_id):
        payment = self.repository.get(gateway_id)
        return GatewayResult(payment.id, payment.status, payment.amount, 'RUB', payment.order_id,
                             payment.confirmation_url)

    def refund(self, payment):
        return 'demo-refund-' + payment.id, 'succeeded'


def payment_service() -> PaymentService:
    repository = SqlPaymentRepository(SessionLocal)
    gateways = {
        'demo': DemoGateway(repository),
        'yookassa': YooKassaGateway(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY,
                                   settings.PUBLIC_URL.rstrip('/') + '/orders'),
    }
    return PaymentService(repository, gateways[settings.PAYMENT_PROVIDER], gateways)
