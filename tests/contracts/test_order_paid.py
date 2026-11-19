"""Pact async message: independently defined kitchen expectation vs real producer."""
import json
from pathlib import Path

import pytest
from pact import Pact, Verifier, match

from app.domain.events import OrderPaid, Receipt, parse_event
from app.memory_storage import InMemoryStorage
from app.modules.kitchen.repository import InMemoryKitchenRepository
from app.modules.kitchen.service import KitchenService
from app.modules.orders.repository import InMemoryOrderRepository
from app.modules.orders.service import OrderService
from tests.conftest import RecordingNotifier, add_order, add_user

DESCRIPTION = 'an order paid event for kitchen'


@pytest.fixture
def contract(tmp_path):
    # Consumer expectations are intentionally not derived from producer.to_payload().
    pact = Pact('sirius-kitchen', 'sirius-orders').with_specification('V4')
    (pact.upon_receiving(DESCRIPTION, 'Async').with_body({
        'event_type': 'order.paid', 'order_id': match.int(1),
        'customer_id': match.int(1), 'amount': match.number(300.0),
        'event_id': match.str('receipt-1'),
        'occurred_at': match.str('2026-11-19T10:00:00+00:00'),
    }, 'application/json'))

    def consume(body, metadata):
        event = parse_event(json.loads(body))
        assert isinstance(event, OrderPaid)
        kitchen = KitchenService(InMemoryKitchenRepository(InMemoryStorage()))
        ticket = kitchen.accept(event, Receipt(consumer='kitchen', event_id=event.event_id))
        assert ticket.order_id == event.order_id

    pact.verify(consume, 'Async')
    pact.write_file(tmp_path, overwrite=True)
    return next(tmp_path.glob('*.json'))


def produced_message():
    storage = InMemoryStorage()
    user = add_user(storage, balance=1000)
    order = add_order(storage, user.id, 1, 'processing', total_cost=300)
    OrderService(InMemoryOrderRepository(storage), RecordingNotifier()).pay_order(order.id, user)
    return storage.outbox[0].to_payload()


def verify(contract, payload):
    return (Verifier('sirius-orders')
            .message_handler({DESCRIPTION: {'contents': json.dumps(payload).encode(), 'content_type': 'application/json', 'metadata': {'contentType': 'application/json'}}})
            .add_source(contract).verify())


def test_real_producer_matches_kitchen_contract(contract):
    verify(contract, produced_message())
    # Keep a reviewable generated Pact; tests still generate their own fresh contract.
    out = Path('docs/lab10/pacts'); out.mkdir(parents=True, exist_ok=True)
    (out / contract.name).write_bytes(contract.read_bytes())


def test_renaming_amount_breaks_provider_contract(contract):
    payload = produced_message()
    payload['total'] = payload.pop('amount')
    with pytest.raises(RuntimeError):
        verify(contract, payload)
