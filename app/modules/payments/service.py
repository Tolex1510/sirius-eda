"""Сценарии внешней оплаты. Сеть и БД скрыты за контрактами."""
from datetime import UTC, datetime
from app.domain.entities import Role, User
from app.domain.exceptions import AccessDeniedError, BusinessRuleError
from app.domain.money import money
from app.modules.payments.contracts import GatewayUnavailable, Payment, PaymentGateway, PaymentRepository
from app.core.observability import orders_created, start_span
import structlog


class PaymentService:
    def __init__(self, repository: PaymentRepository, gateway: PaymentGateway, gateways=None):
        self.repository = repository
        self.gateway = gateway
        self.gateways = gateways or {}

    def create_order(self, actor: User, item_id: int, quantity: int, correlation_id: str | None = None):
        if actor.role != Role.STUDENT:
            raise AccessDeniedError("Оформлять заказы может студент")
        if quantity < 1 or quantity > 100:
            raise BusinessRuleError("Количество должно быть от 1 до 100")
        with start_span("orders.checkout") as span:
            if correlation_id:
                span.set_attribute("app.correlation_id", correlation_id)
            if correlation_id is None:
                order = self.repository.create_order(actor, item_id, quantity)
            else:
                order = self.repository.create_order(actor, item_id, quantity, correlation_id)
            orders_created.inc()
            structlog.get_logger(__name__).info(
                "order_created", order_id=order.id, user_id=actor.id, correlation_id=correlation_id,
            )
            return order

    def get(self, payment_id: str, actor: User) -> Payment:
        payment = self.repository.get(payment_id)
        if actor.id != payment.user_id and actor.role != Role.ADMIN:
            raise AccessDeniedError("Нет доступа к чужому платежу")
        return payment

    def create(self, actor: User, order_id: int, key: str, amount) -> Payment:
        payment = self.repository.reserve(actor, order_id, key, self.gateway.name, amount)
        if payment.gateway_id or payment.status in ('succeeded', 'canceled'):
            return payment
        # Намерение и постоянный ключ уже записаны. Таймаут не превращаем в отказ.
        self._check_window(payment.created_at, payment.provider)
        result = self._gateway_for(payment).create(payment)
        return self._apply(payment, result)

    def sync(self, payment: Payment) -> Payment:
        gateway = self._gateway_for(payment)
        if not payment.gateway_id:
            self._check_window(payment.created_at, payment.provider)
        result = gateway.fetch(payment.gateway_id) if payment.gateway_id else gateway.create(payment)
        updated = self._apply(payment, result)
        if updated.refund_status == 'pending':
            if not updated.refund_id:
                self._check_window(updated.refund_started_at, updated.provider)
            refund_id, status = gateway.refund(updated)
            self.repository.refund_result(updated.id, refund_id, status)
        return self.repository.get(payment.id)

    def _gateway_for(self, payment):
        if payment.provider == self.gateway.name:
            return self.gateway
        gateway = self.gateways.get(payment.provider)
        if not gateway:
            raise GatewayUnavailable("Для сверки этого платежа настройте исходного провайдера")
        return gateway

    def webhook(self, gateway_id: str) -> Payment | None:
        # Тело уведомления не является доказательством оплаты: перечитываем объект через API.
        payment = self.repository.get_by_gateway(gateway_id)
        if payment:
            return self.sync(payment)
        # Если webhook обогнал сохранение gateway_id, периодическая сверка восстановит результат.

    def refund_webhook(self, refund_id: str) -> Payment | None:
        payment = self.repository.get_by_refund(refund_id)
        if payment:
            return self.sync(payment)

    def on_order_cancelled(self, event, receipt):
        # Намерение возврата и Inbox фиксируются атомарно. Вызов шлюза выполнит worker.
        return self.repository.request_refund(event, receipt)

    def _apply(self, payment, result):
        if result.currency != 'RUB' or money(result.amount) != payment.amount or result.order_id != payment.order_id:
            raise BusinessRuleError("Данные провайдера не совпадают с платежом")
        return self.repository.apply(payment.id, result)

    @staticmethod
    def _check_window(started_at, provider):
        if provider != "demo" and started_at and (datetime.now(UTC) - started_at.replace(tzinfo=UTC)).total_seconds() >= 23 * 3600:
            raise GatewayUnavailable("Окно безопасного повтора истекло. Нужна ручная сверка у провайдера")

    def reconcile(self):
        errors = 0
        for payment in self.repository.pending():
            try:
                self.sync(payment)
            except (GatewayUnavailable, BusinessRuleError):
                errors += 1
        return errors
