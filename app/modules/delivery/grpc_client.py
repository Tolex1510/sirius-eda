"""
gRPC-клиент микросервиса доставки (круг 3: Interface Adapters).
Прячет сеть за DeliveryGateway: роутер получает те же сущности и доменные ошибки,
что и от кода в процессе монолита.
"""
import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import grpc

import delivery_pb2
import delivery_pb2_grpc
from app.core.config import settings
from app.core.jwt import create_internal_token
from app.domain.entities import Delivery, User
from app.domain.exceptions import AccessDeniedError, AuthenticationError, BusinessRuleError, NotFoundError
from app.modules.delivery.gateway import DeliveryGateway, DeliveryTimeoutError, DeliveryUnavailableError

ERROR_BY_STATUS = {
    grpc.StatusCode.NOT_FOUND: NotFoundError,
    grpc.StatusCode.PERMISSION_DENIED: AccessDeniedError,
    grpc.StatusCode.FAILED_PRECONDITION: BusinessRuleError,
    grpc.StatusCode.UNAUTHENTICATED: AuthenticationError,
}

# Повтор только для чтения: повторное назначение курьера или завершение доставки
# после потерянного ответа выполнили бы действие дважды.
SERVICE_CONFIG = json.dumps({
    "methodConfig": [{
        "name": [
            {"service": "delivery.DeliveryService", "method": "GetDelivery"},
            {"service": "delivery.DeliveryService", "method": "ListMyDeliveries"},
            {"service": "delivery.DeliveryService", "method": "TrackDelivery"},
        ],
        "retryPolicy": {
            "maxAttempts": 3,
            "initialBackoff": "0.1s",
            "maxBackoff": "1s",
            "backoffMultiplier": 2,
            "retryableStatusCodes": ["UNAVAILABLE"],
        },
    }],
})


@dataclass
class ChatMessage:
    delivery_id: int
    author_id: int
    author_role: str
    text: str
    sent_at: datetime


def create_channel(target: str) -> grpc.Channel:
    return grpc.insecure_channel(target, options=[
        ("grpc.service_config", SERVICE_CONFIG),
        # Пинг держит долгий стрим живым через NAT и прокси.
        ("grpc.keepalive_time_ms", 30_000),
    ])


def to_domain_error(error: grpc.RpcError) -> Exception:
    code = error.code()
    if code == grpc.StatusCode.DEADLINE_EXCEEDED:
        return DeliveryTimeoutError("Сервис доставки не ответил вовремя")
    if code in ERROR_BY_STATUS:
        return ERROR_BY_STATUS[code](error.details())
    if code == grpc.StatusCode.UNAVAILABLE:
        return DeliveryUnavailableError("Сервис доставки недоступен")
    # INTERNAL, UNKNOWN и прочее: проблема на стороне сервиса, клиент тут ни при чём.
    return DeliveryUnavailableError(f"Ошибка сервиса доставки: {code.name}")


def to_entity(message: delivery_pb2.Delivery) -> Delivery:
    return Delivery(
        id=message.id,
        order_id=message.order_id,
        courier_id=message.courier_id if message.HasField("courier_id") else None,
        status=message.status,
    )


class GrpcDeliveryGateway(DeliveryGateway):
    def __init__(self, channel: grpc.Channel, timeout: float):
        self.stub = delivery_pb2_grpc.DeliveryServiceStub(channel)
        self.timeout = timeout

    @staticmethod
    def _metadata(actor: User) -> tuple:
        return (("authorization", f"Bearer {create_internal_token(actor.id)}"),)

    def _unary(self, method, request, actor: User):
        try:
            # Без таймаута упавший сервис держал бы поток монолита до разрыва TCP.
            return method(request, timeout=self.timeout, metadata=self._metadata(actor))
        except grpc.RpcError as e:
            raise to_domain_error(e) from e

    def assign_courier(self, order_id: int, courier_id: int, actor: User) -> int:
        request = delivery_pb2.AssignCourierRequest(order_id=order_id, courier_id=courier_id)
        return self._unary(self.stub.AssignCourier, request, actor).delivery_id

    def pick_up(self, delivery_id: int, actor: User) -> Delivery:
        request = delivery_pb2.PickUpOrderRequest(delivery_id=delivery_id)
        return to_entity(self._unary(self.stub.PickUpOrder, request, actor))

    def complete_delivery(self, delivery_id: int, actor: User) -> None:
        self._unary(self.stub.CompleteDelivery, delivery_pb2.CompleteDeliveryRequest(delivery_id=delivery_id), actor)

    def get_delivery(self, delivery_id: int, actor: User) -> Delivery:
        request = delivery_pb2.GetDeliveryRequest(delivery_id=delivery_id)
        return to_entity(self._unary(self.stub.GetDelivery, request, actor))

    def list_my_deliveries(self, actor: User) -> list[Delivery]:
        response = self._unary(self.stub.ListMyDeliveries, delivery_pb2.ListMyDeliveriesRequest(), actor)
        return [to_entity(d) for d in response.deliveries]

    def track(self, delivery_id: int, actor: User) -> Iterator[Delivery]:
        # У стрима нет общего таймаута: доставка идёт столько, сколько идёт.
        stream = self.stub.TrackDelivery(
            delivery_pb2.TrackDeliveryRequest(delivery_id=delivery_id), metadata=self._metadata(actor)
        )
        try:
            for status in stream:
                yield to_entity(status.delivery)
        except grpc.RpcError as e:
            raise to_domain_error(e) from e
        finally:
            stream.cancel()

    def chat(self, delivery_id: int, actor: User, outgoing: Iterator[str]) -> Iterator[ChatMessage]:
        """Bidirectional stream: строки из outgoing уходят в чат, входящие сообщения возвращаются по мере прихода."""
        def requests():
            # Первое сообщение выбирает доставку, сервер не рассылает его, если текст пустой.
            yield delivery_pb2.ChatMessage(delivery_id=delivery_id)
            for text in outgoing:
                yield delivery_pb2.ChatMessage(delivery_id=delivery_id, text=text)

        stream = self.stub.ChatWithCourier(requests(), metadata=self._metadata(actor))
        try:
            for message in stream:
                yield ChatMessage(
                    delivery_id=message.delivery_id,
                    author_id=message.author_id,
                    author_role=message.author_role,
                    text=message.text,
                    sent_at=message.sent_at.ToDatetime(tzinfo=UTC),
                )
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.CANCELLED:
                raise to_domain_error(e) from e
        finally:
            stream.cancel()


_channel: grpc.Channel | None = None
_channel_lock = threading.Lock()


def delivery_grpc_gateway() -> GrpcDeliveryGateway:
    """
    Один канал на процесс: он держит HTTP/2-соединение и сам переподключается.
    Канал на каждый запрос, как в методичке, платил бы за TCP и HTTP/2 handshake каждый раз.
    """
    global _channel
    with _channel_lock:
        if _channel is None:
            _channel = create_channel(settings.DELIVERY_GRPC_TARGET)
    return GrpcDeliveryGateway(_channel, settings.DELIVERY_GRPC_TIMEOUT)


def close_delivery_channel() -> None:
    global _channel
    with _channel_lock:
        if _channel is not None:
            _channel.close()
            _channel = None
