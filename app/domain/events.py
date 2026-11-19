"""
Доменные события «Сириус.Еды». Сервис фиксирует факт, а кто на него реагирует, не знает.
Не зависят от брокера: в RabbitMQ события попадают через outbox.
"""
from dataclasses import MISSING, asdict, dataclass, field, fields
from datetime import UTC, datetime
from types import UnionType
from typing import ClassVar
from typing import get_args, get_origin
from uuid import uuid4


class InvalidEventError(ValueError):
    """Сообщение нельзя разобрать. Повтор не поможет: такое сообщение сразу уходит в DLQ."""


@dataclass(frozen=True, kw_only=True)
class Event:
    ROUTING_KEY: ClassVar[str]

    # Ключ идемпотентности: по нему получатель узнаёт повторную доставку.
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str | None = None

    def to_payload(self) -> dict:
        payload = asdict(self)
        if self.correlation_id is None:
            payload.pop("correlation_id", None)
        payload["occurred_at"] = self.occurred_at.isoformat()
        payload["event_type"] = self.ROUTING_KEY
        return payload

    @classmethod
    def from_payload(cls, payload: dict) -> "Event":
        values = {}
        for f in fields(cls):
            if f.name not in payload:
                if f.default is not MISSING:
                    values[f.name] = f.default
                    continue
                if f.default_factory is not MISSING:
                    values[f.name] = f.default_factory()
                    continue
                raise InvalidEventError(f"Нет поля {f.name}")
            values[f.name] = _check(f.name, f.type, payload[f.name])
        return cls(**values)


@dataclass(frozen=True, kw_only=True)
class OrderPaid(Event):
    ROUTING_KEY: ClassVar[str] = "order.paid"

    order_id: int
    customer_id: int
    amount: float


@dataclass(frozen=True, kw_only=True)
class DeliveryFailed(Event):
    """Доставку создать не удалось. Шаг саги: заказ отменяется, деньги возвращаются."""
    ROUTING_KEY: ClassVar[str] = "delivery.failed"

    order_id: int
    reason: str


@dataclass(frozen=True, kw_only=True)
class OrderCancelled(Event):
    ROUTING_KEY: ClassVar[str] = "order.cancelled"

    order_id: int
    customer_id: int
    refund: float
    reason: str


EVENT_TYPES: dict[str, type[Event]] = {cls.ROUTING_KEY: cls for cls in (OrderPaid, DeliveryFailed, OrderCancelled)}


@dataclass(frozen=True)
class Receipt:
    """Отметка «получатель обработал событие». Пишется в одной транзакции с результатом обработки."""
    consumer: str
    event_id: str


def parse_event(payload: object) -> Event:
    if not isinstance(payload, dict):
        raise InvalidEventError("Событие должно быть JSON-объектом")
    event_type = EVENT_TYPES.get(payload.get("event_type"))
    if not event_type:
        raise InvalidEventError(f"Неизвестный тип события {payload.get('event_type')!r}")
    return event_type.from_payload(payload)


def _check(name: str, expected: type, value: object) -> object:
    origin = get_origin(expected)
    if value is None and origin in (UnionType,) and type(None) in get_args(expected):
        return None
    if origin is UnionType:
        expected = next((arg for arg in get_args(expected) if arg is not type(None)), expected)
    if expected is datetime:
        try:
            parsed = datetime.fromisoformat(value)
        except (TypeError, ValueError):
            raise InvalidEventError(f"Поле {name}: ожидается дата ISO 8601")
        if parsed.tzinfo is None:
            raise InvalidEventError(f"Поле {name}: дата без часового пояса")
        return parsed
    # bool наследует int, но order_id = true это ошибка отправителя.
    if isinstance(value, bool) or not isinstance(value, (int, float) if expected is float else expected):
        raise InvalidEventError(f"Поле {name}: ожидается {expected.__name__}")
    if expected is str and not value:
        raise InvalidEventError(f"Поле {name} пустое")
    return float(value) if expected is float else value
