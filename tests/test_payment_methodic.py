"""Проверки пунктов трека D: amount, вебхуки, Saga, повторы и DLQ."""
from dataclasses import replace
import json
import logging
from decimal import Decimal
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.domain.events import OrderCancelled, Receipt
from app.domain.exceptions import AlreadyProcessedError, BusinessRuleError
from app.models import Order, OutboxEvent, Payment as PaymentRow
from app.modules.payments.contracts import GatewayRejected, GatewayResult, GatewayUnavailable, PaymentConflict
from app.modules.payments.dependencies import DemoGateway
from app.modules.payments.gateway import YooKassaGateway
from tests.test_payments import checkout, consume_cancellations, succeed, world


class ControlledGateway(DemoGateway):
    name = 'yookassa'

    def __init__(self, repository):
        super().__init__(repository)
        self.status = 'pending'
        self.reason = None
        self.refund_status = 'pending'
        self.fetch_calls = 0
        self.refund_calls = 0

    def fetch(self, gateway_id):
        self.fetch_calls += 1
        payment = self.repository.get(gateway_id)
        return GatewayResult(payment.id, self.status, payment.amount, 'RUB', payment.order_id,
                             cancellation_reason=self.reason)

    def refund(self, payment):
        self.refund_calls += 1
        return 'refund-' + payment.id, self.refund_status


@pytest.fixture
def payment_api(world, monkeypatch):
    from app.main import app
    from app.core.dependencies import get_current_user
    from app.modules.payments.dependencies import payment_service
    sessions, service, alice, _, item_id = world
    gateway = ControlledGateway(service.repository)
    service.gateway = gateway
    monkeypatch.setattr(settings, 'YOOKASSA_SHOP_ID', 'fake-shop')
    monkeypatch.setattr(settings, 'YOOKASSA_SECRET_KEY', 'fake-secret')
    previous = app.dependency_overrides.copy()
    app.dependency_overrides.update({payment_service: lambda: service, get_current_user: lambda: alice})
    try:
        with TestClient(app) as client:
            yield client, gateway
    finally:
        app.dependency_overrides = previous


def payment_via_api(world, client):
    _, service, alice, _, item = world
    order = service.create_order(alice, item, 3)
    response = client.post('/payments', json={'order_id': order.id, 'amount': '0.30'},
                           headers={'Idempotency-Key': 'methodic-payment'})
    assert response.status_code == 200
    return order, response.json()


def notify(client, kind, external_id, **extra):
    return client.post('/payments/webhook', json={'type': 'notification', 'event': kind,
                                                'object': {'id': external_id, **extra}})


def test_amount_is_required_and_must_match_server_order(world, payment_api):
    sessions, service, alice, _, item = world
    client, _ = payment_api
    order = service.create_order(alice, item, 3)
    headers = {'Idempotency-Key': 'methodic-amount'}
    for amount in [None, 'NaN', '0.001', '-1']:
        body = {'order_id': order.id}
        if amount is not None: body['amount'] = amount
        assert client.post('/payments', json=body, headers=headers).status_code == 422
    assert client.post('/payments', json={'order_id': order.id, 'amount': '0.31'}, headers=headers).status_code == 409
    with sessions() as db:
        assert db.query(PaymentRow).count() == 0
    valid = client.post('/payments', json={'order_id': order.id, 'amount': '0.30'}, headers=headers)
    duplicate = client.post('/payments', json={'order_id': order.id, 'amount': '0.30'}, headers=headers)
    assert valid.status_code == duplicate.status_code == 200
    assert valid.json()['id'] == duplicate.json()['id']
    assert valid.json()['amount'] == '0.30'
    assert client.post('/payments', json={'order_id': order.id, 'amount': '0.31'}, headers=headers).status_code == 409


def test_webhook_rechecks_provider_and_applies_duplicate_payment_once(world, payment_api):
    sessions, service, *_ = world
    client, gateway = payment_api
    order, payment = payment_via_api(world, client)
    # Поддельное тело не меняет фактический pending у провайдера.
    assert notify(client, 'payment.succeeded', payment['gateway_id'], status='succeeded').status_code == 200
    assert service.repository.get(payment['id']).status == 'pending'
    gateway.status = 'succeeded'
    for _ in range(3):
        assert notify(client, 'payment.succeeded', payment['gateway_id']).status_code == 200
    with sessions() as db:
        assert db.get(Order, order.id).status == 'paid'
        assert db.query(OutboxEvent).filter_by(routing_key='order.paid').count() == 1
    assert gateway.fetch_calls == 4


def test_webhook_log_uses_verified_status_and_excludes_raw_payload(world, payment_api, monkeypatch, caplog):
    from app.modules.payments.telemetry import logger
    monkeypatch.setattr(logger, 'handlers', [caplog.handler])
    client, gateway = payment_api
    order, payment = payment_via_api(world, client)
    with caplog.at_level(logging.INFO, logger=logger.name):
        assert notify(client, 'payment.succeeded', payment['gateway_id'],
                      status='succeeded', secret='do-not-log-this').status_code == 200
    record = json.loads(next(r.message for r in caplog.records if r.name == logger.name))
    assert record['event'] == 'payment.succeeded'
    assert record['order_id'] == order.id
    assert record['payment_status'] == 'pending'  # Входящее утверждение не подменяет статус PSP.
    assert record['result'] == 'processed'
    assert record['http_status'] == 200
    assert record['duration_ms'] >= 0
    assert 'do-not-log-this' not in caplog.text
    assert 'fake-secret' not in caplog.text


def test_webhook_log_distinguishes_unknown_object_and_provider_failure(world, payment_api, monkeypatch, caplog):
    from app.modules.payments.telemetry import logger
    monkeypatch.setattr(logger, 'handlers', [caplog.handler])
    client, gateway = payment_api
    _, payment = payment_via_api(world, client)
    with caplog.at_level(logging.INFO, logger=logger.name):
        assert notify(client, 'payment.succeeded', 'unknown-object').status_code == 200
        monkeypatch.setattr(gateway, 'fetch', Mock(side_effect=GatewayUnavailable('sensitive-provider-detail')))
        assert notify(client, 'payment.succeeded', payment['gateway_id']).status_code == 503
    records = [json.loads(r.message) for r in caplog.records if r.name == logger.name]
    assert [(r['result'], r['http_status']) for r in records] == [('ignored', 200), ('failed', 503)]
    assert all(r['order_id'] is None for r in records)
    assert 'sensitive-provider-detail' not in caplog.text


def test_failed_payment_notification_saves_insufficient_funds(world, payment_api):
    sessions, service, *_ = world
    client, gateway = payment_api
    order, payment = payment_via_api(world, client)
    gateway.status = 'canceled'
    gateway.reason = 'insufficient_funds'
    for _ in range(2): assert notify(client, 'payment.canceled', payment['gateway_id']).status_code == 200
    saved = service.repository.get(payment['id'])
    assert saved.status == 'canceled'
    assert saved.cancellation_reason == 'insufficient_funds'
    with sessions() as db:
        assert db.get(Order, order.id).status == 'processing'
        assert db.query(OutboxEvent).filter_by(routing_key='order.paid').count() == 0


def test_refund_notification_is_verified_and_idempotent(world, payment_api):
    sessions, service, alice, *_ = world
    client, gateway = payment_api
    order, payment = payment_via_api(world, client)
    gateway.status = 'succeeded'
    notify(client, 'payment.succeeded', payment['gateway_id'])
    service.repository.cancel(alice, order.id)
    assert service.repository.get(payment['id']).refund_status is None
    consume_cancellations(world)
    service.sync(service.repository.get(payment['id']))
    saved = service.repository.get(payment['id'])
    assert saved.refund_status == 'pending'
    # Одного утверждения из уведомления недостаточно — провайдер всё ещё отвечает pending.
    notify(client, 'refund.succeeded', saved.refund_id)
    assert service.repository.get(saved.id).refund_status == 'pending'
    gateway.refund_status = 'succeeded'
    notify(client, 'refund.succeeded', saved.refund_id)
    calls = gateway.refund_calls
    notify(client, 'refund.succeeded', saved.refund_id)
    assert service.repository.get(saved.id).refund_status == 'succeeded'
    assert gateway.refund_calls == calls
    with sessions() as db:
        assert db.query(OutboxEvent).filter_by(routing_key='order.cancelled').count() == 1


def test_order_cancelled_receipt_and_refund_intention_are_idempotent(world):
    sessions, service, alice, *_ = world
    order, payment = checkout(world)
    succeed(service, payment)
    service.repository.cancel(alice, order.id)
    with sessions() as db:
        payload = db.scalar(select(OutboxEvent).where(OutboxEvent.routing_key == 'order.cancelled')).payload
    event = OrderCancelled.from_payload(payload)
    receipt = Receipt('payments', event.event_id)
    requested = service.on_order_cancelled(event, receipt)
    assert requested.refund_status == 'pending'
    with pytest.raises(AlreadyProcessedError): service.on_order_cancelled(event, receipt)
    # Другая копия логической отмены с новым event_id тоже не сбрасывает возврат.
    duplicate = replace(event, event_id='another-cancellation')
    assert service.on_order_cancelled(duplicate, Receipt('payments', duplicate.event_id)) is None
    assert service.repository.get(payment.id).refund_started_at == requested.refund_started_at.replace(tzinfo=None)


def test_cancellation_event_cannot_refund_an_active_order(world):
    _, service, alice, *_ = world
    order, payment = checkout(world)
    succeed(service, payment)
    event = OrderCancelled(order_id=order.id, customer_id=alice.id, refund=.30, reason='Forged')
    with pytest.raises(BusinessRuleError): service.on_order_cancelled(event, Receipt('payments', event.event_id))
    assert service.repository.get(payment.id).refund_status is None


@pytest.mark.parametrize('status,expected', [(400, GatewayRejected), (401, GatewayRejected), (429, GatewayUnavailable), (500, GatewayUnavailable), (503, GatewayUnavailable)])
def test_gateway_retries_only_transient_http_errors(status, expected):
    gateway = YooKassaGateway('shop', 'secret', 'http://localhost/orders',
                             transport=httpx.MockTransport(lambda _: httpx.Response(status, json={'code': 'test'})))
    with pytest.raises(expected): gateway.fetch('gateway-payment')


def test_timeout_after_remote_acceptance_reuses_gateway_key(world):
    _, service, alice, *_ = world
    order, pending = checkout(world)
    calls = []
    def handle(request):
        calls.append(request.headers['Idempotence-Key'])
        if len(calls) == 1: raise httpx.ReadTimeout('Response lost', request=request)
        return httpx.Response(200, json={'id': 'accepted-payment', 'status': 'pending', 'test': True,
                                        'amount': {'value': '0.30', 'currency': 'RUB'},
                                        'metadata': {'order_id': str(order.id)}})
    gateway = YooKassaGateway('shop', 'secret', 'http://localhost/orders', transport=httpx.MockTransport(handle))
    with pytest.raises(GatewayUnavailable): gateway.create(pending)
    assert gateway.create(pending).id == 'accepted-payment'
    assert calls == [pending.id, pending.id]


@pytest.mark.parametrize("error,attempts", [(GatewayUnavailable("Unavailable"), 5), (GatewayRejected("Invalid request"), 1)])
def test_payment_retries_then_enters_dlq_and_manual_review(world, monkeypatch, error, attempts):
    from app import database
    from app.core.celery_app import celery_app, DEAD_LETTER_QUEUE
    from app.tasks import payments as tasks
    from app.tasks.dead_letters import list_dead_letters
    sessions, service, *_ = world
    _, payment = checkout(world)
    gateway = Mock(); gateway.name = 'demo'; gateway.fetch.side_effect = error
    service.gateway = gateway
    monkeypatch.setattr(tasks, 'payment_service', lambda: service)
    monkeypatch.setattr(database, 'SessionLocal', sessions)
    monkeypatch.setitem(celery_app.conf, 'broker_url', 'memory://')
    with celery_app.connection_for_write() as connection:
        connection.SimpleQueue(DEAD_LETTER_QUEUE).clear()
    result = tasks.sync_payment.apply(args=[payment.id], throw=False)
    assert result.failed()
    assert gateway.fetch.call_count == attempts
    assert service.repository.get(payment.id).review_required
    [letter] = list_dead_letters()
    assert letter['task'] == tasks.sync_payment.name
    assert letter['args'] == [payment.id]


def test_refund_intention_survives_celery_publish_failure(world, monkeypatch):
    from kombu.exceptions import OperationalError
    from app.workers import payments_consumer
    sessions, service, alice, *_ = world
    order, payment = checkout(world)
    succeed(service, payment)
    service.repository.cancel(alice, order.id)
    with sessions() as db:
        event = OrderCancelled.from_payload(db.scalar(select(OutboxEvent).where(
            OutboxEvent.routing_key == 'order.cancelled')).payload)
    monkeypatch.setattr(payments_consumer, 'payment_service', lambda: service)
    monkeypatch.setattr(payments_consumer.sync_payment, 'delay', Mock(side_effect=OperationalError('Redis unavailable')))
    with pytest.raises(OperationalError):
        payments_consumer.on_order_cancelled(event, Receipt('payments', event.event_id))
    assert service.repository.get(payment.id).refund_status == 'pending'
    service.reconcile()
    assert service.repository.get(payment.id).refund_status == 'succeeded'
