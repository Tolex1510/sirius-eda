import pytest

from app.domain.entities import MenuItem, OrderStatus, Role, User
from app.domain.exceptions import AccessDeniedError, BusinessRuleError, NotFoundError
from app.modules.orders.repository import InMemoryOrderRepository
from app.modules.orders.service import OrderService
from tests.conftest import RecordingNotifier, add_menu_item, add_user


@pytest.fixture
def service(storage, notifier) -> OrderService:
    return OrderService(InMemoryOrderRepository(storage), notifier)


def test_create_order_charges_balance(service, storage):
    user = add_user(storage, balance=500)
    item = add_menu_item(storage, price=150)

    order_id = service.create_order(user.id, item.id, quantity=2)

    assert storage.users[user.id].balance == 200
    order = storage.orders[order_id]
    assert (order.user_id, order.item_id, order.quantity) == (user.id, item.id, 2)
    assert order.status == OrderStatus.PROCESSING
    assert order.total_cost == 300


def test_unknown_user(service, storage):
    item = add_menu_item(storage)

    with pytest.raises(NotFoundError, match="Пользователь не найден"):
        service.create_order(999, item.id, quantity=1)


def test_unknown_menu_item(service, storage):
    user = add_user(storage, balance=500)

    with pytest.raises(NotFoundError, match="Блюдо не найдено"):
        service.create_order(user.id, 999, quantity=1)


def test_unavailable_menu_item(service, storage):
    user = add_user(storage, balance=500)
    item = add_menu_item(storage, is_available=False)

    with pytest.raises(BusinessRuleError, match="Блюдо недоступно"):
        service.create_order(user.id, item.id, quantity=1)


def test_insufficient_funds_leaves_state_untouched(service, storage):
    user = add_user(storage, balance=100)
    item = add_menu_item(storage, price=150)

    with pytest.raises(BusinessRuleError, match="Недостаточно средств"):
        service.create_order(user.id, item.id, quantity=1)

    assert storage.users[user.id].balance == 100
    assert storage.orders == {}


def test_service_depends_only_on_abstraction():
    class FakeRepository:
        def __init__(self):
            self.saved = None

        def get_user_by_id(self, user_id):
            return User(id=user_id, email="a@b.ru", phone=None, balance=1000, is_blocked=False)

        def get_menu_item_by_id(self, item_id):
            return MenuItem(id=item_id, name="Борщ", price=100, is_available=True)

        def save_order(self, user_id, item_id, quantity, total_cost, new_balance):
            self.saved = (user_id, item_id, quantity, total_cost, new_balance)
            return 42

    repository = FakeRepository()

    assert OrderService(repository, RecordingNotifier()).create_order(1, 2, quantity=3) == 42
    assert repository.saved == (1, 2, 3, 300, 700)


def test_new_order_triggers_notifications(service, storage, notifier):
    user = add_user(storage, balance=500)
    order_id = service.create_order(user.id, add_menu_item(storage).id, quantity=1)

    assert notifier.created == [(order_id, user.id)]


def test_rejected_order_sends_nothing(service, storage, notifier):
    user = add_user(storage, balance=10)

    with pytest.raises(BusinessRuleError):
        service.create_order(user.id, add_menu_item(storage, price=100).id, quantity=1)

    assert notifier.created == []


def test_cancel_own_order_refunds_price_paid(service, storage):
    user = add_user(storage, balance=500)
    item = add_menu_item(storage, price=150)
    order_id = service.create_order(user.id, item.id, quantity=2)
    storage.menu_items[item.id].price = 999

    service.cancel_order(order_id, actor=user)

    assert storage.orders[order_id].status == OrderStatus.CANCELLED
    assert storage.users[user.id].balance == 500


def test_cancel_foreign_order_is_forbidden(service, storage):
    owner = add_user(storage, balance=500)
    stranger = add_user(storage, balance=500)
    order_id = service.create_order(owner.id, add_menu_item(storage).id, quantity=1)

    with pytest.raises(AccessDeniedError, match="чужому заказу"):
        service.cancel_order(order_id, actor=stranger)

    assert storage.orders[order_id].status == OrderStatus.PROCESSING
    assert storage.users[owner.id].balance == 400


def test_cancel_twice_refunds_once(service, storage):
    user = add_user(storage, balance=500)
    order_id = service.create_order(user.id, add_menu_item(storage).id, quantity=1)
    service.cancel_order(order_id, actor=user)

    with pytest.raises(BusinessRuleError):
        service.cancel_order(order_id, actor=user)
    assert storage.users[user.id].balance == 500


def test_admin_can_cancel_any_order(service, storage):
    owner = add_user(storage, balance=500)
    admin = add_user(storage, role=Role.ADMIN)
    order_id = service.create_order(owner.id, add_menu_item(storage).id, quantity=1)

    service.cancel_order(order_id, actor=admin)

    assert storage.users[owner.id].balance == 500


def test_kitchen_sees_only_active_orders(service, storage):
    user = add_user(storage, balance=500)
    item = add_menu_item(storage)
    active = service.create_order(user.id, item.id, quantity=1)
    cancelled = service.create_order(user.id, item.id, quantity=1)
    service.cancel_order(cancelled, actor=user)

    assert [o.id for o in service.get_kitchen_orders()] == [active]
