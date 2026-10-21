import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Delivery(_message.Message):
    __slots__ = ("id", "order_id", "courier_id", "status")
    ID_FIELD_NUMBER: _ClassVar[int]
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    COURIER_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    id: int
    order_id: int
    courier_id: int
    status: str
    def __init__(self, id: _Optional[int] = ..., order_id: _Optional[int] = ..., courier_id: _Optional[int] = ..., status: _Optional[str] = ...) -> None: ...

class AssignCourierRequest(_message.Message):
    __slots__ = ("order_id", "courier_id")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    COURIER_ID_FIELD_NUMBER: _ClassVar[int]
    order_id: int
    courier_id: int
    def __init__(self, order_id: _Optional[int] = ..., courier_id: _Optional[int] = ...) -> None: ...

class AssignCourierResponse(_message.Message):
    __slots__ = ("delivery_id", "status")
    DELIVERY_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    delivery_id: int
    status: str
    def __init__(self, delivery_id: _Optional[int] = ..., status: _Optional[str] = ...) -> None: ...

class PickUpOrderRequest(_message.Message):
    __slots__ = ("delivery_id",)
    DELIVERY_ID_FIELD_NUMBER: _ClassVar[int]
    delivery_id: int
    def __init__(self, delivery_id: _Optional[int] = ...) -> None: ...

class CompleteDeliveryRequest(_message.Message):
    __slots__ = ("delivery_id",)
    DELIVERY_ID_FIELD_NUMBER: _ClassVar[int]
    delivery_id: int
    def __init__(self, delivery_id: _Optional[int] = ...) -> None: ...

class CompleteDeliveryResponse(_message.Message):
    __slots__ = ("status",)
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: str
    def __init__(self, status: _Optional[str] = ...) -> None: ...

class GetDeliveryRequest(_message.Message):
    __slots__ = ("delivery_id",)
    DELIVERY_ID_FIELD_NUMBER: _ClassVar[int]
    delivery_id: int
    def __init__(self, delivery_id: _Optional[int] = ...) -> None: ...

class ListMyDeliveriesRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListMyDeliveriesResponse(_message.Message):
    __slots__ = ("deliveries",)
    DELIVERIES_FIELD_NUMBER: _ClassVar[int]
    deliveries: _containers.RepeatedCompositeFieldContainer[Delivery]
    def __init__(self, deliveries: _Optional[_Iterable[_Union[Delivery, _Mapping]]] = ...) -> None: ...

class TrackDeliveryRequest(_message.Message):
    __slots__ = ("delivery_id",)
    DELIVERY_ID_FIELD_NUMBER: _ClassVar[int]
    delivery_id: int
    def __init__(self, delivery_id: _Optional[int] = ...) -> None: ...

class DeliveryStatus(_message.Message):
    __slots__ = ("delivery", "changed_at")
    DELIVERY_FIELD_NUMBER: _ClassVar[int]
    CHANGED_AT_FIELD_NUMBER: _ClassVar[int]
    delivery: Delivery
    changed_at: _timestamp_pb2.Timestamp
    def __init__(self, delivery: _Optional[_Union[Delivery, _Mapping]] = ..., changed_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ChatMessage(_message.Message):
    __slots__ = ("delivery_id", "text", "author_id", "author_role", "sent_at")
    DELIVERY_ID_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_ID_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_ROLE_FIELD_NUMBER: _ClassVar[int]
    SENT_AT_FIELD_NUMBER: _ClassVar[int]
    delivery_id: int
    text: str
    author_id: int
    author_role: str
    sent_at: _timestamp_pb2.Timestamp
    def __init__(self, delivery_id: _Optional[int] = ..., text: _Optional[str] = ..., author_id: _Optional[int] = ..., author_role: _Optional[str] = ..., sent_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...
