from decimal import Decimal

from sqlalchemy import func, select
from app.models import MenuItem, Order, OutboxEvent, User


def create(client, account, **changes):
    _, item_id, headers = account
    return client.post('/orders/create', headers=headers,
                       json=dict(item_id=item_id, quantity=2, **changes))


def test_http_order_persists_total_and_balance(sql_client, sql_sessions, account):
    response = create(sql_client, account)
    assert response.status_code == 200  # actual API contract, not methodic's illustrative 201
    with sql_sessions() as db:
        order = db.get(Order, response.json()['order_id'])
        assert order.user_id == account[0]
        assert order.quantity == 2
        assert order.total_cost == Decimal('300.00')
        assert order.status == 'processing'
        assert db.get(User, account[0]).balance == Decimal('700.00')


def test_insufficient_balance_has_no_partial_write(sql_client, sql_sessions, account):
    with sql_sessions.begin() as db:
        db.get(User, account[0]).balance = 100
    assert create(sql_client, account).status_code == 400
    with sql_sessions() as db:
        assert db.scalar(select(func.count()).select_from(Order)) == 0
        assert db.get(User, account[0]).balance == Decimal('100.00')


def test_unavailable_item_is_rejected(sql_client, sql_sessions, account):
    with sql_sessions.begin() as db:
        db.get(MenuItem, account[1]).is_available = False
    assert create(sql_client, account).status_code == 400
    with sql_sessions() as db:
        assert db.scalar(select(func.count()).select_from(Order)) == 0
        assert db.get(User, account[0]).balance == Decimal('1000.00')


def test_cancel_refunds_once(sql_client, sql_sessions, account):
    order_id = create(sql_client, account).json()['order_id']
    first = sql_client.post(f'/orders/{order_id}/cancel', headers=account[2])
    second = sql_client.post(f'/orders/{order_id}/cancel', headers=account[2])
    assert first.status_code == 200
    assert second.status_code == 400
    with sql_sessions() as db:
        assert db.get(User, account[0]).balance == Decimal('1000.00')
        assert db.get(Order, order_id).status == 'cancelled'


def test_payment_and_outbox_commit_together(sql_client, sql_sessions, account):
    order_id = create(sql_client, account).json()['order_id']
    response = sql_client.post(f'/orders/{order_id}/pay', headers=account[2])
    assert response.status_code == 200
    with sql_sessions() as db:
        assert db.get(Order, order_id).status == 'paid'
        event = db.scalars(select(OutboxEvent)).one()
        assert event.payload['order_id'] == order_id
        assert event.payload['event_type'] == 'order.paid'
        assert event.payload['amount'] == 300


def test_without_authentication_no_order(sql_client, sql_sessions, account):
    assert sql_client.post('/orders/create', json={'item_id':account[1], 'quantity':1}).status_code == 401
    with sql_sessions() as db:
        assert db.scalar(select(func.count()).select_from(Order)) == 0


def test_database_is_clean_between_tests(sql_sessions):
    with sql_sessions() as db:
        assert db.scalar(select(func.count()).select_from(Order)) == 0
        assert db.scalar(select(func.count()).select_from(User)) == 0
