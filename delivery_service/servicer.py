"""
gRPC-адаптер микросервиса доставки: переводит сообщения Protobuf в вызовы DeliveryService,
а доменные ошибки в коды gRPC. Бизнес-правила остались в DeliveryService, здесь только транспорт.
"""
import itertools
import logging
import queue
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

import delivery_pb2
import delivery_pb2_grpc
from app.core.jwt import INTERNAL, InvalidTokenError, decode_token
from app.domain.entities import Delivery, DeliveryStatus, User
from app.domain.exceptions import AccessDeniedError, AuthenticationError, DomainError, NotFoundError
from app.modules.delivery.repository import DeliveryRepository
from app.modules.delivery.service import DeliveryService
from delivery_service.realtime import ChatRooms, StatusBoard

logger = logging.getLogger("delivery_service")

STATUS_BY_ERROR = (
    (AuthenticationError, grpc.StatusCode.UNAUTHENTICATED),
    (NotFoundError, grpc.StatusCode.NOT_FOUND),
    (AccessDeniedError, grpc.StatusCode.PERMISSION_DENIED),
)
# Статус мог изменить другой экземпляр сервиса или монолит в режиме local.
# Таких изменений StatusBoard не видит, поэтому стрим перечитывает БД не реже этого.
TRACK_RECHECK_SECONDS = 2.0
MAX_CHAT_TEXT = 1000

RepositoryScope = Callable[[], AbstractContextManager[DeliveryRepository]]


def status_for(error: DomainError) -> grpc.StatusCode:
    # Остальные доменные ошибки это нарушенные бизнес-правила: состояние не позволяет действие.
    return next((code for cls, code in STATUS_BY_ERROR if isinstance(error, cls)), grpc.StatusCode.FAILED_PRECONDITION)


def delivery_message(delivery: Delivery) -> delivery_pb2.Delivery:
    return delivery_pb2.Delivery(
        id=delivery.id, order_id=delivery.order_id, courier_id=delivery.courier_id, status=delivery.status
    )


def now() -> Timestamp:
    stamp = Timestamp()
    stamp.GetCurrentTime()
    return stamp


class DeliveryServicer(delivery_pb2_grpc.DeliveryServiceServicer):
    def __init__(self, repository_scope: RepositoryScope):
        self.repository_scope = repository_scope
        self.board = StatusBoard()
        self.chat = ChatRooms()

    @contextmanager
    def _call(self, context: grpc.ServicerContext, method: str) -> Iterator[tuple[DeliveryService, User]]:
        """Сервис на свежем репозитории и пользователь из метаданных. Ошибки в коды gRPC, строка в лог."""
        started = time.perf_counter()
        code = grpc.StatusCode.OK
        try:
            with self.repository_scope() as repository:
                yield DeliveryService(repository), self._actor(context, repository)
        except DomainError as e:
            code = status_for(e)
            context.abort(code, str(e))
        except Exception:
            code = grpc.StatusCode.INTERNAL
            logger.exception("%s failed", method)
            context.abort(code, "Внутренняя ошибка сервиса доставки")
        finally:
            logger.info("%s %s %.1f ms", method, code.name, (time.perf_counter() - started) * 1000)

    @staticmethod
    def _actor(context: grpc.ServicerContext, repository: DeliveryRepository) -> User:
        """
        Пользователь, от имени которого вызывает монолит. Сервис не верит вызывающему на слово:
        проверяет подпись токена и читает роль и блокировку из БД.
        """
        scheme, _, token = dict(context.invocation_metadata()).get("authorization", "").partition(" ")
        try:
            if scheme.lower() != "bearer":
                raise InvalidTokenError()
            user_id = decode_token(token, INTERNAL)
        except InvalidTokenError:
            raise AuthenticationError("Нет действующего токена пользователя")
        # get_courier_by_id возвращает пользователя с любой ролью.
        user = repository.get_courier_by_id(user_id)
        if not user:
            raise AuthenticationError("Пользователь не найден")
        if user.is_blocked:
            raise AccessDeniedError("Пользователь заблокирован")
        return user

    def AssignCourier(self, request, context):
        with self._call(context, "AssignCourier") as (service, actor):
            delivery_id = service.assign_courier(request.order_id, request.courier_id, actor=actor)
        self.board.changed()
        return delivery_pb2.AssignCourierResponse(delivery_id=delivery_id, status=DeliveryStatus.IN_PROGRESS)

    def PickUpOrder(self, request, context):
        with self._call(context, "PickUpOrder") as (service, actor):
            delivery = service.pick_up(request.delivery_id, actor=actor)
        self.board.changed()
        return delivery_message(delivery)

    def CompleteDelivery(self, request, context):
        with self._call(context, "CompleteDelivery") as (service, actor):
            service.complete_delivery(request.delivery_id, actor=actor)
        self.board.changed()
        return delivery_pb2.CompleteDeliveryResponse(status=DeliveryStatus.COMPLETED)

    def GetDelivery(self, request, context):
        with self._call(context, "GetDelivery") as (service, actor):
            delivery = service.get_delivery(request.delivery_id, actor=actor)
        return delivery_message(delivery)

    def ListMyDeliveries(self, request, context):
        with self._call(context, "ListMyDeliveries") as (service, actor):
            deliveries = service.list_my_deliveries(actor)
        return delivery_pb2.ListMyDeliveriesResponse(deliveries=[delivery_message(d) for d in deliveries])

    def TrackDelivery(self, request, context):
        # Версию берём до чтения: изменение между чтением и ожиданием не потеряется.
        seen = self.board.version
        with self._call(context, "TrackDelivery") as (service, actor):
            delivery = service.get_delivery(request.delivery_id, actor=actor)

        last_status = None
        while context.is_active():
            if delivery.status != last_status:
                last_status = delivery.status
                yield delivery_pb2.DeliveryStatus(delivery=delivery_message(delivery), changed_at=now())
            if delivery.status in DeliveryStatus.FINAL:
                return
            seen = self.board.wait(seen, TRACK_RECHECK_SECONDS)
            # Права проверены при подписке, дальше только свежий статус.
            with self.repository_scope() as repository:
                delivery = repository.get_by_id(delivery.id)

    def ChatWithCourier(self, request_iterator, context):
        first = next(request_iterator, None)
        if first is None:
            return
        # Писать в чат могут те же, кто видит доставку: курьер, заказчик, администратор.
        with self._call(context, "ChatWithCourier") as (service, actor):
            delivery = service.get_delivery(first.delivery_id, actor=actor)

        inbox = self.chat.join(delivery.id)
        context.add_callback(lambda: inbox.put(None))
        messages = itertools.chain([first], request_iterator)
        threading.Thread(target=self._receive, args=(messages, delivery.id, actor, inbox), daemon=True).start()
        try:
            while (message := inbox.get()) is not None:
                yield message
        finally:
            self.chat.leave(delivery.id, inbox)

    def _receive(self, messages: Iterator, room: int, author: User, inbox: queue.Queue) -> None:
        """Читает сообщения клиента в своём потоке, пока поток ответа отдаёт ему чужие."""
        try:
            for message in messages:
                text = message.text.strip()[:MAX_CHAT_TEXT]
                if text:
                    self.chat.publish(room, delivery_pb2.ChatMessage(
                        delivery_id=room, text=text, author_id=author.id, author_role=author.role, sent_at=now()
                    ))
        except grpc.RpcError:
            # Клиент оборвал соединение.
            pass
        finally:
            inbox.put(None)
