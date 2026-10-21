"""
Микросервис доставки по-настоящему: gRPC-сервер на свободном порту, клиент ходит к нему по сети.
Данные в памяти, PostgreSQL не нужен.
"""
import queue
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import grpc
import pytest

import delivery_pb2
from app.core.jwt import create_access_token, create_internal_token
from app.domain.entities import DeliveryStatus, OrderStatus, Role
from app.domain.exceptions import AccessDeniedError, BusinessRuleError, NotFoundError
from app.modules.delivery import grpc_client
from app.modules.delivery.gateway import DeliveryTimeoutError, DeliveryUnavailableError, LocalDeliveryGateway
from app.modules.delivery.grpc_client import GrpcDeliveryGateway, create_channel
from app.modules.delivery.repository import InMemoryDeliveryRepository
from app.modules.delivery.service import DeliveryService
from delivery_service import servicer as servicer_module
from delivery_service.server import build_server
from delivery_service.servicer import DeliveryServicer
from tests.conftest import add_delivery, add_menu_item, add_order, add_user

ROOT = Path(__file__).parent.parent


def memory_scope(storage):
    @contextmanager
    def scope():
        yield InMemoryDeliveryRepository(storage)
    return scope


@contextmanager
def running(servicer: DeliveryServicer):
    server, port = build_server(servicer, "127.0.0.1:0")
    server.start()
    channel = create_channel(f"127.0.0.1:{port}")
    try:
        yield GrpcDeliveryGateway(channel, timeout=2)
    finally:
        channel.close()
        server.stop(0)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def servicer(storage) -> DeliveryServicer:
    return DeliveryServicer(memory_scope(storage))


@pytest.fixture
def remote(servicer):
    with running(servicer) as gateway:
        yield gateway


@pytest.fixture(params=["local", "grpc"])
def gateway(request, storage):
    """Один и тот же сценарий на коде монолита и на микросервисе: Strangler Fig меняет путь, а не поведение."""
    if request.param == "local":
        yield LocalDeliveryGateway(DeliveryService(InMemoryDeliveryRepository(storage)))
    else:
        yield request.getfixturevalue("remote")


@pytest.fixture
def people(storage):
    customer = add_user(storage)
    courier = add_user(storage, role=Role.COURIER)
    order = add_order(storage, customer.id, add_menu_item(storage).id, OrderStatus.PAID)
    return customer, courier, order


def test_delivery_lifecycle(gateway, storage, people):
    customer, courier, order = people

    delivery_id = gateway.assign_courier(order.id, courier.id, actor=courier)
    assert gateway.get_delivery(delivery_id, actor=customer).status == DeliveryStatus.IN_PROGRESS
    assert [d.id for d in gateway.list_my_deliveries(courier)] == [delivery_id]
    assert gateway.pick_up(delivery_id, actor=courier).status == DeliveryStatus.ON_THE_WAY
    gateway.complete_delivery(delivery_id, actor=courier)

    delivery = gateway.get_delivery(delivery_id, actor=customer)
    assert (delivery.order_id, delivery.courier_id, delivery.status) == (order.id, courier.id, DeliveryStatus.COMPLETED)
    assert storage.orders[order.id].status == OrderStatus.DELIVERED


def test_domain_errors_cross_the_network(gateway, storage, people):
    customer, courier, order = people
    delivery = add_delivery(storage, order.id, courier.id, DeliveryStatus.COMPLETED)

    with pytest.raises(NotFoundError, match="Доставка не найдена"):
        gateway.get_delivery(999, actor=customer)
    with pytest.raises(AccessDeniedError, match="чужой доставке"):
        gateway.get_delivery(delivery.id, actor=add_user(storage))
    with pytest.raises(BusinessRuleError, match="уже завершена"):
        gateway.complete_delivery(delivery.id, actor=courier)


def test_courier_id_is_empty_until_assigned(remote, storage, people):
    customer, _, order = people
    delivery = add_delivery(storage, order.id, None, DeliveryStatus.PENDING)

    assert remote.get_delivery(delivery.id, actor=customer).courier_id is None


def test_service_checks_token_itself(servicer, storage, people):
    customer, *_ = people
    with running(servicer) as gateway:
        stub = gateway.stub
        request = delivery_pb2.ListMyDeliveriesRequest()
        for metadata in [(), (("authorization", "Bearer forged"),),
                         (("authorization", f"Bearer {create_access_token(customer.id)}"),)]:
            with pytest.raises(grpc.RpcError) as error:
                stub.ListMyDeliveries(request, metadata=metadata, timeout=2)
            assert error.value.code() == grpc.StatusCode.UNAUTHENTICATED

        valid = (("authorization", f"Bearer {create_internal_token(customer.id)}"),)
        assert stub.ListMyDeliveries(request, metadata=valid, timeout=2).deliveries == []


def test_blocked_user_is_rejected_by_service(remote, storage):
    blocked = add_user(storage, is_blocked=True)

    with pytest.raises(AccessDeniedError, match="заблокирован"):
        remote.list_my_deliveries(blocked)


def test_unavailable_service_fails_fast(storage):
    customer = add_user(storage)
    channel = create_channel(f"127.0.0.1:{free_port()}")
    gateway = GrpcDeliveryGateway(channel, timeout=2)

    started = time.perf_counter()
    for call in (lambda: gateway.get_delivery(1, actor=customer), lambda: gateway.assign_courier(1, 1, actor=customer)):
        with pytest.raises(DeliveryUnavailableError, match="недоступен"):
            call()
    channel.close()

    assert time.perf_counter() - started < 2


def test_slow_service_hits_deadline(storage, people):
    customer, courier, order = people
    delivery = add_delivery(storage, order.id, courier.id, DeliveryStatus.IN_PROGRESS)

    class SlowServicer(DeliveryServicer):
        def GetDelivery(self, request, context):
            time.sleep(0.5)
            return super().GetDelivery(request, context)

    with running(SlowServicer(memory_scope(storage))) as gateway:
        gateway.timeout = 0.1
        with pytest.raises(DeliveryTimeoutError):
            gateway.get_delivery(delivery.id, actor=customer)


def test_unexpected_server_error_is_not_leaked(storage):
    customer = add_user(storage)

    @contextmanager
    def broken_scope():
        raise RuntimeError("connection to database lost")
        yield

    with running(DeliveryServicer(broken_scope)) as gateway:
        with pytest.raises(DeliveryUnavailableError, match="INTERNAL") as error:
            gateway.list_my_deliveries(customer)
    assert "database" not in str(error.value)


def collect(iterator, into: queue.Queue):
    def run():
        try:
            for item in iterator:
                into.put(item)
        except Exception as e:
            into.put(e)
        into.put(None)
    threading.Thread(target=run, daemon=True).start()


def test_track_streams_every_status_change(remote, storage, people):
    customer, courier, order = people
    delivery_id = remote.assign_courier(order.id, courier.id, actor=courier)
    updates = queue.Queue()
    collect(remote.track(delivery_id, customer), updates)

    assert updates.get(timeout=2).status == DeliveryStatus.IN_PROGRESS
    remote.pick_up(delivery_id, actor=courier)
    assert updates.get(timeout=1).status == DeliveryStatus.ON_THE_WAY
    remote.complete_delivery(delivery_id, actor=courier)
    assert updates.get(timeout=1).status == DeliveryStatus.COMPLETED
    assert updates.get(timeout=1) is None


def test_track_sees_changes_made_outside_the_service(remote, storage, people, monkeypatch):
    monkeypatch.setattr(servicer_module, "TRACK_RECHECK_SECONDS", 0.1)
    customer, courier, order = people
    delivery = add_delivery(storage, order.id, courier.id, DeliveryStatus.IN_PROGRESS)
    updates = queue.Queue()
    collect(remote.track(delivery.id, customer), updates)
    assert updates.get(timeout=2).status == DeliveryStatus.IN_PROGRESS

    storage.deliveries[delivery.id].status = DeliveryStatus.CANCELLED

    assert updates.get(timeout=2).status == DeliveryStatus.CANCELLED


def test_track_foreign_delivery_is_forbidden(gateway, storage, people):
    _, courier, order = people
    delivery = add_delivery(storage, order.id, courier.id, DeliveryStatus.IN_PROGRESS)

    with pytest.raises(AccessDeniedError):
        next(gateway.track(delivery.id, add_user(storage)))


def chat_session(gateway, delivery_id, actor):
    outgoing, incoming = queue.Queue(), queue.Queue()
    collect(gateway.chat(delivery_id, actor, iter(outgoing.get, None)), incoming)
    return outgoing, incoming


def test_customer_and_courier_chat(remote, servicer, storage, people):
    customer, courier, order = people
    delivery = add_delivery(storage, order.id, courier.id, DeliveryStatus.ON_THE_WAY)
    customer_out, customer_in = chat_session(remote, delivery.id, customer)
    courier_out, courier_in = chat_session(remote, delivery.id, courier)
    for _ in range(100):
        if len(servicer.chat._members[delivery.id]) == 2:
            break
        time.sleep(0.02)

    customer_out.put("Где мой заказ?")
    for inbox in (customer_in, courier_in):
        message = inbox.get(timeout=2)
        assert (message.text, message.author_id, message.author_role) == ("Где мой заказ?", customer.id, Role.STUDENT)

    courier_out.put("Буду через 5 минут")
    assert customer_in.get(timeout=2).text == "Буду через 5 минут"

    customer_out.put(None)
    courier_out.put(None)
    assert customer_in.get(timeout=2) is None


def test_late_participant_sees_history(remote, storage, people):
    customer, courier, order = people
    delivery = add_delivery(storage, order.id, courier.id, DeliveryStatus.ON_THE_WAY)
    customer_out, customer_in = chat_session(remote, delivery.id, customer)
    customer_out.put("Позвоните в домофон 12")
    customer_in.get(timeout=2)

    _, courier_in = chat_session(remote, delivery.id, courier)

    assert courier_in.get(timeout=2).text == "Позвоните в домофон 12"
    customer_out.put(None)


def test_stranger_cannot_join_chat(remote, storage, people):
    _, courier, order = people
    delivery = add_delivery(storage, order.id, courier.id, DeliveryStatus.ON_THE_WAY)
    _, incoming = chat_session(remote, delivery.id, add_user(storage))

    assert isinstance(incoming.get(timeout=2), AccessDeniedError)


def test_api_returns_503_when_delivery_service_is_down(client, storage):
    from app import dependencies
    from app.main import app
    from tests.conftest import create_account

    _, courier = create_account(client, storage, Role.COURIER)
    channel = create_channel(f"127.0.0.1:{free_port()}")
    app.dependency_overrides[dependencies.get_delivery_gateway] = lambda: GrpcDeliveryGateway(channel, timeout=1)

    response = client.post("/delivery/assign", json={"order_id": 1, "courier_id": 1}, headers=courier)
    channel.close()

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert response.json() == {"detail": "Сервис доставки недоступен"}


def test_track_over_http_uses_server_sent_events(client, storage):
    from tests.conftest import create_account

    customer_id, customer = create_account(client, storage)
    _, stranger = create_account(client, storage)
    courier = add_user(storage, role=Role.COURIER)
    order = add_order(storage, customer_id, add_menu_item(storage).id, OrderStatus.DELIVERED)
    delivery = add_delivery(storage, order.id, courier.id, DeliveryStatus.COMPLETED)

    response = client.get(f"/delivery/{delivery.id}/track", headers=customer)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text == (
        f'event: status\ndata: {{"delivery_id": {delivery.id}, "courier_id": {courier.id}, "status": "completed"}}\n\n'
    )
    assert client.get(f"/delivery/{delivery.id}/track", headers=stranger).status_code == 403


def test_monolith_reuses_one_channel(monkeypatch):
    monkeypatch.setattr(grpc_client, "_channel", None)

    grpc_client.delivery_grpc_gateway()
    channel = grpc_client._channel
    grpc_client.delivery_grpc_gateway()

    assert grpc_client._channel is channel is not None
    grpc_client.close_delivery_channel()
    assert grpc_client._channel is None


def test_generated_code_matches_contract(tmp_path):
    subprocess.run(["bash", str(ROOT / "scripts/gen_proto.sh"), str(tmp_path)], check=True,
                   env={"PATH": str(Path(sys.executable).parent) + ":/usr/bin:/bin"})

    for name in ("delivery_pb2.py", "delivery_pb2_grpc.py", "delivery_pb2.pyi"):
        assert (tmp_path / name).read_text() == (ROOT / name).read_text(), f"{name} устарел: запустите scripts/gen_proto.sh"


def test_retries_only_for_reads():
    import json

    [config] = json.loads(grpc_client.SERVICE_CONFIG)["methodConfig"]
    retried = {name["method"] for name in config["name"]}

    assert retried == {"GetDelivery", "ListMyDeliveries", "TrackDelivery"}
