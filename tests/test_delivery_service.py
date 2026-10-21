import pytest

from app.domain.entities import DeliveryStatus, OrderStatus, Role
from app.domain.exceptions import AccessDeniedError, BusinessRuleError, NotFoundError
from app.modules.delivery.repository import InMemoryDeliveryRepository
from app.modules.delivery.service import DeliveryService
from tests.conftest import add_delivery, add_menu_item, add_order, add_user


@pytest.fixture
def service(storage) -> DeliveryService:
    return DeliveryService(InMemoryDeliveryRepository(storage))


@pytest.fixture
def customer(storage):
    return add_user(storage)


@pytest.fixture
def courier(storage):
    return add_user(storage, role=Role.COURIER)


@pytest.fixture
def admin(storage):
    return add_user(storage, role=Role.ADMIN)


@pytest.fixture
def paid_order(storage, customer):
    return add_order(storage, customer.id, add_menu_item(storage).id, OrderStatus.PAID)


def test_courier_takes_paid_order(service, storage, paid_order, courier):
    delivery_id = service.assign_courier(paid_order.id, courier.id, actor=courier)

    assert storage.deliveries[delivery_id].status == DeliveryStatus.IN_PROGRESS


def test_courier_cannot_assign_someone_else(service, storage, paid_order, courier):
    other = add_user(storage, role=Role.COURIER)

    with pytest.raises(AccessDeniedError, match="только себе"):
        service.assign_courier(paid_order.id, other.id, actor=courier)


def test_admin_assigns_any_courier(service, paid_order, courier, admin):
    assert service.assign_courier(paid_order.id, courier.id, actor=admin)


def test_only_courier_role_can_be_assigned(service, paid_order, customer, admin):
    with pytest.raises(BusinessRuleError, match="courier"):
        service.assign_courier(paid_order.id, customer.id, actor=admin)


def test_assign_requires_paid_order(service, storage, customer, courier):
    order = add_order(storage, customer.id, add_menu_item(storage).id, OrderStatus.PROCESSING)

    with pytest.raises(BusinessRuleError, match="оплаченный"):
        service.assign_courier(order.id, courier.id, actor=courier)


def test_assign_unknown_order(service, courier):
    with pytest.raises(NotFoundError, match="Заказ не найден"):
        service.assign_courier(999, courier.id, actor=courier)


def test_assign_blocked_courier(service, storage, paid_order, admin):
    blocked = add_user(storage, role=Role.COURIER, is_blocked=True)

    with pytest.raises(AccessDeniedError):
        service.assign_courier(paid_order.id, blocked.id, actor=admin)


def test_courier_has_single_active_delivery(service, paid_order, courier):
    service.assign_courier(paid_order.id, courier.id, actor=courier)

    with pytest.raises(BusinessRuleError, match="активная доставка"):
        service.assign_courier(paid_order.id, courier.id, actor=courier)


def test_complete_own_delivery_marks_order_delivered(service, storage, paid_order, courier):
    delivery = add_delivery(storage, paid_order.id, courier.id, DeliveryStatus.IN_PROGRESS)

    service.complete_delivery(delivery.id, actor=courier)

    assert storage.deliveries[delivery.id].status == DeliveryStatus.COMPLETED
    assert storage.orders[paid_order.id].status == OrderStatus.DELIVERED


def test_complete_foreign_delivery_is_forbidden(service, storage, paid_order, courier):
    delivery = add_delivery(storage, paid_order.id, courier.id, DeliveryStatus.IN_PROGRESS)
    other = add_user(storage, role=Role.COURIER)

    with pytest.raises(AccessDeniedError):
        service.complete_delivery(delivery.id, actor=other)
    assert storage.deliveries[delivery.id].status == DeliveryStatus.IN_PROGRESS


@pytest.mark.parametrize(
    ("status", "message"),
    [(DeliveryStatus.COMPLETED, "уже завершена"), (DeliveryStatus.CANCELLED, "Отменённую")],
)
def test_complete_rejects_final_statuses(service, storage, paid_order, courier, status, message):
    delivery = add_delivery(storage, paid_order.id, courier.id, status)

    with pytest.raises(BusinessRuleError, match=message):
        service.complete_delivery(delivery.id, actor=courier)


def test_delivery_visible_to_courier_customer_and_admin(service, storage, paid_order, customer, courier, admin):
    delivery = add_delivery(storage, paid_order.id, courier.id, DeliveryStatus.IN_PROGRESS)

    for actor in (customer, courier, admin):
        assert service.get_delivery(delivery.id, actor=actor).id == delivery.id


@pytest.mark.parametrize("role", [Role.STUDENT, Role.COURIER, Role.COOK])
def test_delivery_hidden_from_strangers(service, storage, paid_order, courier, role):
    delivery = add_delivery(storage, paid_order.id, courier.id, DeliveryStatus.IN_PROGRESS)
    stranger = add_user(storage, role=role)

    with pytest.raises(AccessDeniedError, match="чужой доставке"):
        service.get_delivery(delivery.id, actor=stranger)


def test_my_deliveries(service, storage, paid_order, customer, courier):
    mine = add_delivery(storage, paid_order.id, courier.id, DeliveryStatus.IN_PROGRESS)
    other_order = add_order(storage, add_user(storage).id, add_menu_item(storage).id, OrderStatus.PAID)
    add_delivery(storage, other_order.id, add_user(storage, role=Role.COURIER).id, DeliveryStatus.IN_PROGRESS)

    assert [d.id for d in service.list_my_deliveries(courier)] == [mine.id]
    assert [d.id for d in service.list_my_deliveries(customer)] == [mine.id]


def test_pick_up_moves_delivery_on_the_way(service, storage, paid_order, courier):
    delivery = add_delivery(storage, paid_order.id, courier.id, DeliveryStatus.IN_PROGRESS)

    assert service.pick_up(delivery.id, actor=courier).status == DeliveryStatus.ON_THE_WAY
    assert storage.deliveries[delivery.id].status == DeliveryStatus.ON_THE_WAY


def test_pick_up_twice_is_rejected(service, storage, paid_order, courier):
    delivery = add_delivery(storage, paid_order.id, courier.id, DeliveryStatus.ON_THE_WAY)

    with pytest.raises(BusinessRuleError, match="Забрать можно только"):
        service.pick_up(delivery.id, actor=courier)


def test_pick_up_foreign_delivery_is_forbidden(service, storage, paid_order, courier):
    delivery = add_delivery(storage, paid_order.id, courier.id, DeliveryStatus.IN_PROGRESS)

    with pytest.raises(AccessDeniedError):
        service.pick_up(delivery.id, actor=add_user(storage, role=Role.COURIER))


def test_courier_on_the_way_is_busy(service, storage, paid_order, courier):
    add_delivery(storage, paid_order.id, courier.id, DeliveryStatus.ON_THE_WAY)
    other_order = add_order(storage, add_user(storage).id, add_menu_item(storage).id, OrderStatus.PAID)

    with pytest.raises(BusinessRuleError, match="уже есть активная доставка"):
        service.assign_courier(other_order.id, courier.id, actor=courier)


def test_delivery_on_the_way_can_be_completed(service, storage, paid_order, courier):
    delivery = add_delivery(storage, paid_order.id, courier.id, DeliveryStatus.ON_THE_WAY)

    service.complete_delivery(delivery.id, actor=courier)

    assert storage.deliveries[delivery.id].status == DeliveryStatus.COMPLETED
    assert storage.orders[paid_order.id].status == OrderStatus.DELIVERED
