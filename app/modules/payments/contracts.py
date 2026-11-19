"""Независимые от транспорта контракты платежей."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from app.domain.entities import Order, User
from app.domain.events import OrderCancelled, Receipt
from app.domain.exceptions import BusinessRuleError


class PaymentConflict(ValueError):
    pass


class GatewayUnavailable(Exception):
    pass


class GatewayRejected(BusinessRuleError):
    """Окончательная ошибка запроса; сетевой retry её не исправит."""


@dataclass(frozen=True)
class Payment:
    id: str
    order_id: int
    user_id: int
    amount: Decimal
    provider: str
    status: str
    idempotency_key: str
    gateway_id: str | None = None
    confirmation_url: str | None = None
    refund_status: str | None = None
    refund_id: str | None = None
    created_at: datetime | None = None
    refund_started_at: datetime | None = None
    review_required: bool = False
    cancellation_reason: str | None = None


@dataclass(frozen=True)
class GatewayResult:
    id: str
    status: str
    amount: Decimal
    currency: str
    order_id: int
    confirmation_url: str | None = None
    cancellation_reason: str | None = None


class PaymentGateway(ABC):
    name: str

    @abstractmethod
    def create(self, payment: Payment) -> GatewayResult: ...
    @abstractmethod
    def fetch(self, gateway_id: str) -> GatewayResult: ...
    @abstractmethod
    def refund(self, payment: Payment) -> tuple[str, str]: ...


class PaymentRepository(ABC):
    @abstractmethod
    def create_order(
        self, actor: User, item_id: int, quantity: int, correlation_id: str | None = None,
    ) -> Order: ...
    @abstractmethod
    def reserve(self, actor: User, order_id: int, key: str, provider: str, amount: Decimal) -> Payment: ...
    @abstractmethod
    def get(self, payment_id: str) -> Payment: ...
    @abstractmethod
    def get_by_gateway(self, gateway_id: str) -> Payment | None: ...
    @abstractmethod
    def get_by_refund(self, refund_id: str) -> Payment | None: ...
    @abstractmethod
    def apply(self, payment_id: str, result: GatewayResult) -> Payment: ...
    @abstractmethod
    def cancel(self, actor: User, order_id: int) -> None: ...
    @abstractmethod
    def request_refund(self, event: OrderCancelled, receipt: Receipt) -> Payment | None: ...
    @abstractmethod
    def refund_result(self, payment_id: str, refund_id: str, status: str) -> None: ...
    @abstractmethod
    def pending(self) -> list[Payment]: ...
    @abstractmethod
    def list_for(self, actor: User) -> list[Payment]: ...
