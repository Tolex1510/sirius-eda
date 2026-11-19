from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock
import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base
from app.domain.entities import Role
from app.domain.events import OrderCancelled, OrderPaid, Receipt, DeliveryFailed, parse_event
from app.domain.exceptions import AccessDeniedError, AlreadyProcessedError, BusinessRuleError
from app.models import User, Role as RoleRow, MenuItem, Order, Payment as PaymentRow, OutboxEvent, Delivery
from app.modules.orders.repository import SqlAlchemyOrderRepository
from app.modules.orders.service import OrderService
from app.modules.payments.contracts import GatewayResult, GatewayUnavailable, PaymentConflict
from app.modules.payments.dependencies import DemoGateway
from app.modules.payments.gateway import YooKassaGateway
from app.modules.payments.repository import SqlPaymentRepository
from app.modules.payments.service import PaymentService
from tests.conftest import RecordingNotifier


@pytest.fixture
def world():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions.begin() as db:
        role = RoleRow(name=Role.STUDENT)
        db.add(role); db.flush()
        users = [User(email=f'{n}@test.ru', balance=100, is_blocked=False, role_id=role.id) for n in ['alice', 'bob']]
        db.add_all(users); db.flush()
        actors = [u.to_entity() for u in users]
        item = MenuItem(name='Тестовое блюдо', price=Decimal('0.10'), is_available=True)
        db.add(item); db.flush()
        item_id = item.id
    repository = SqlPaymentRepository(sessions)
    service = PaymentService(repository, DemoGateway(repository))
    yield sessions, service, actors[0], actors[1], item_id
    engine.dispose()


def checkout(world):
    _, service, alice, _, item = world
    order = service.create_order(alice, item, 3)
    payment = service.create(alice, order.id, 'test-key-1', Decimal('0.30'))
    return order, payment


def succeed(service, payment):
    return service._apply(payment, GatewayResult(payment.id, 'succeeded', payment.amount, 'RUB', payment.order_id))


def consume_cancellations(world):
    sessions, service, *_ = world
    with sessions() as db:
        events = [parse_event(row.payload) for row in db.scalars(
            select(OutboxEvent).where(OutboxEvent.routing_key == 'order.cancelled').order_by(OutboxEvent.id))]
    for event in events:
        try:
            service.on_order_cancelled(event, Receipt('payments', event.event_id))
        except AlreadyProcessedError:
            pass


def test_checkout_does_not_charge_balance_and_calculates_decimal(world):
    sessions, service, alice, _, item = world
    order = service.create_order(alice, item, 3)
    with sessions() as db:
        assert db.get(User, alice.id).balance == 100
        assert db.get(Order, order.id).total_cost == Decimal('0.30')
        assert db.query(OutboxEvent).count() == 0
    assert order.payment_source == 'gateway'


def test_payment_and_outbox_transition_happen_once(world):
    sessions, service, alice, _, _ = world
    order, payment = checkout(world)
    assert service.create(alice, order.id, 'test-key-1', Decimal('0.30')).id == payment.id
    succeed(service, payment); succeed(service, payment)
    # Устаревшее pending не откатывает succeeded.
    service._apply(payment, GatewayResult(payment.id, 'pending', payment.amount, 'RUB', order.id))
    with sessions() as db:
        assert db.get(Order, order.id).status == 'paid'
        assert db.query(PaymentRow).count() == 1
        [event] = db.scalars(select(OutboxEvent))
        assert event.routing_key == OrderPaid.ROUTING_KEY
        assert event.payload['amount'] == 0.3


def test_keys_cannot_duplicate_payment_or_move_to_another_order(world):
    _, service, alice, _, item = world
    order, _ = checkout(world)
    with pytest.raises(PaymentConflict):
        service.create(alice, order.id, 'another-key', Decimal('0.30'))
    second = service.create_order(alice, item, 1)
    with pytest.raises(PaymentConflict):
        service.create(alice, second.id, 'test-key-1', Decimal('0.10'))


def test_foreign_payment_is_inaccessible(world):
    _, service, _, bob, _ = world
    order, payment = checkout(world)
    for operation in [lambda: service.get(payment.id, bob), lambda: service.create(bob, order.id, 'test-key-1', Decimal('0.30')),
                      lambda: service.repository.cancel(bob, order.id)]:
        with pytest.raises(AccessDeniedError): operation()


@pytest.mark.parametrize('field,value', [('amount', Decimal('10')), ('currency', 'USD'), ('order_id', 999)])
def test_provider_result_is_checked_against_server_amount(world, field, value):
    _, service, _, _, _ = world
    order, payment = checkout(world)
    values = dict(id=payment.id, status='succeeded', amount=payment.amount, currency='RUB', order_id=order.id)
    values[field] = value
    with pytest.raises(BusinessRuleError): service._apply(payment, GatewayResult(**values))
    assert service.repository.get(payment.id).status == 'pending'


def test_legacy_pay_cannot_confirm_external_checkout(world):
    sessions, _, alice, _, _ = world
    order, _ = checkout(world)
    with sessions() as db:
        with pytest.raises(BusinessRuleError, match='провайдер'):
            OrderService(SqlAlchemyOrderRepository(db), RecordingNotifier()).pay_order(order.id, alice)


def test_cancel_before_success_refunds_late_payment_without_dispatch(world):
    sessions, service, alice, _, _ = world
    order, payment = checkout(world)
    service.repository.cancel(alice, order.id)
    consume_cancellations(world)
    assert service.repository.get(payment.id).refund_status is None
    succeed(service, payment)
    consume_cancellations(world)
    service.sync(service.repository.get(payment.id))
    with sessions() as db:
        assert db.get(Order, order.id).status == 'cancelled'
        assert db.get(User, alice.id).balance == 100
        assert db.get(PaymentRow, payment.id).refund_status == 'succeeded'
        assert db.query(OutboxEvent).filter_by(routing_key='order.paid').count() == 0


def test_cancel_paid_and_repeated_refund_are_idempotent(world):
    sessions, service, alice, _, _ = world
    order, payment = checkout(world)
    succeed(service, payment)
    service.repository.cancel(alice, order.id)
    service.repository.cancel(alice, order.id)
    assert service.repository.get(payment.id).refund_status is None
    consume_cancellations(world)
    service.reconcile(); service.reconcile()
    with sessions() as db:
        assert db.get(PaymentRow, payment.id).refund_status == 'succeeded'
        assert db.get(User, alice.id).balance == 100
        assert db.query(OutboxEvent).filter_by(routing_key='order.cancelled').count() == 1


def test_delivery_failure_requests_gateway_refund_not_balance_credit(world):
    sessions, service, alice, _, _ = world
    order, payment = checkout(world)
    succeed(service, payment)
    with sessions() as db:
        orders = OrderService(SqlAlchemyOrderRepository(db), RecordingNotifier())
        event = DeliveryFailed(order_id=order.id, reason='Нет курьера')
        orders.compensate_failed_delivery(event, Receipt('orders', event.event_id))
    assert service.repository.get(payment.id).refund_status is None
    consume_cancellations(world)
    service.reconcile()
    with sessions() as db:
        assert db.get(User, alice.id).balance == 100
        assert db.get(PaymentRow, payment.id).refund_status == 'succeeded'


def test_cancel_rejected_when_delivery_is_on_the_way(world):
    sessions, service, alice, _, _ = world
    order, payment = checkout(world)
    succeed(service, payment)
    with sessions.begin() as db:
        db.add(Delivery(order_id=order.id, courier_id=alice.id, status='on_the_way'))
    with pytest.raises(BusinessRuleError): service.repository.cancel(alice, order.id)


def test_unknown_result_reuses_intention_and_timeout_does_not_mark_failed(world):
    sessions, service, alice, _, _ = world
    order, payment = checkout(world)
    with sessions.begin() as db:
        row = db.get(PaymentRow, payment.id); row.gateway_id = None; row.status = 'creating'; row.provider = 'yookassa'
    gateway = Mock(name='gateway'); gateway.name = 'yookassa'; gateway.create.side_effect = GatewayUnavailable()
    service.gateway = gateway
    with pytest.raises(GatewayUnavailable): service.create(alice, order.id, 'test-key-1', Decimal('0.30'))
    assert service.repository.get(payment.id).status == 'creating'
    gateway.create.assert_called_once()


def test_creation_is_never_replayed_after_provider_window(world):
    sessions, service, alice, _, _ = world
    order, payment = checkout(world)
    with sessions.begin() as db:
        row = db.get(PaymentRow, payment.id)
        row.provider = 'yookassa'; row.gateway_id = None; row.status = 'creating'
        row.created_at = datetime.now(UTC) - timedelta(days=2)
    gateway = Mock(); gateway.name = 'yookassa'; service.gateway = gateway
    with pytest.raises(GatewayUnavailable, match='истекло'): service.create(alice, order.id, 'test-key-1', Decimal('0.30'))
    gateway.create.assert_not_called()


def test_yookassa_adapter_sends_persistent_key_and_checks_test_mode(world):
    _, _, _, _, _ = world
    order, payment = checkout(world)
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={'id': 'gateway-1', 'status': 'pending', 'test': True,
                                        'amount': {'value': '0.30', 'currency': 'RUB'},
                                        'metadata': {'order_id': str(order.id)}})
    gateway = YooKassaGateway('shop', 'secret', 'http://localhost/orders', transport=httpx.MockTransport(respond))
    assert gateway.create(payment).amount == Decimal('0.30')
    assert requests[0].headers['Idempotence-Key'] == payment.id
    assert requests[0].url.path == '/v3/payments'
    assert 'secret' not in str(requests[0].url)
    gateway.transport = httpx.MockTransport(lambda r: httpx.Response(200, json={'test': False}))
    with pytest.raises(GatewayUnavailable): gateway.create(payment)


def test_original_gateway_is_used_after_default_changes(world):
    _, service, alice, _, _ = world
    order, payment = checkout(world)
    original = service.gateway
    service.gateways = {'demo': original}
    replacement = Mock(); replacement.name = 'yookassa'
    service.gateway = replacement
    assert service.create(alice, order.id, 'test-key-1', Decimal('0.30')).id == payment.id
    assert service.sync(payment).provider == 'demo'
    replacement.create.assert_not_called()
    replacement.fetch.assert_not_called()


def test_review_flag_stops_automatic_scheduling_until_successful_manual_check(world):
    _, service, _, _, _ = world
    _, payment = checkout(world)
    service.repository.mark_review(payment.id)
    assert service.repository.pending() == []
    assert service.repository.get(payment.id).review_required is True
    service.sync(service.repository.get(payment.id))
    assert service.repository.get(payment.id).review_required is False


def test_worker_retry_uses_exponential_delay_without_blocking_http(monkeypatch):
    from celery.exceptions import Retry
    from app.tasks import payments as tasks
    fake = Mock()
    fake.sync.side_effect = GatewayUnavailable('Временный сбой')
    monkeypatch.setattr(tasks, 'payment_service', lambda: fake)
    tasks.sync_payment.push_request(retries=2, is_eager=True, called_directly=False)
    try:
        with pytest.raises(Retry) as retry:
            tasks.sync_payment.run('payment-id')
        assert 4 <= retry.value.when <= 4.5
    finally:
        tasks.sync_payment.pop_request()


def test_refund_checks_currency_and_keeps_stable_operation_key(world):
    _, service, _, _, _ = world
    _, payment = checkout(world)
    captured = []
    def respond(request):
        captured.append(request)
        return httpx.Response(200, json={'id': 'refund-1', 'payment_id': payment.gateway_id,
                                        'status': 'succeeded', 'amount': {'value': str(payment.amount), 'currency': 'USD'}})
    gateway = YooKassaGateway('shop', 'secret', 'http://localhost/orders', transport=httpx.MockTransport(respond))
    with pytest.raises(GatewayUnavailable): gateway.refund(payment)
    assert captured[0].headers['Idempotence-Key'] == 'refund-' + payment.id


def test_late_manual_delivery_assignment_cannot_revive_cancelled_order(world):
    from app.modules.delivery.repository import SqlAlchemyDeliveryRepository
    sessions, service, alice, _, _ = world
    order, payment = checkout(world)
    succeed(service, payment)
    service.repository.cancel(alice, order.id)
    with sessions() as db:
        with pytest.raises(BusinessRuleError, match='отменён'):
            SqlAlchemyDeliveryRepository(db).create(order.id, alice.id, 'in_progress')
        assert db.query(Delivery).filter_by(order_id=order.id).count() == 0
