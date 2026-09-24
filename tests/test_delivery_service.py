import pytest

from app.domain.entities import DeliveryStatus, OrderStatus
from app.domain.exceptions import AccessDeniedError, BusinessRuleError, NotFoundError
from app.modules.delivery.repository import InMemoryDeliveryRepository
from app.modules.delivery.service import DeliveryService
from tests.conftest import add_delivery, add_menu_item, add_order, add_user


@pytest.fixture
def service(storage) -> DeliveryService:
    return DeliveryService(InMemoryDeliveryRepository(storage))


@pytest.fixture
def paid_order(storage):
    return add_order(storage, add_user(storage).id, add_menu_item(storage).id, OrderStatus.PAID)


def test_assign_courier_to_paid_order(service, storage, paid_order):
    courier = add_user(storage)

    delivery_id = service.assign_courier(paid_order.id, courier.id)

    assert storage.deliveries[delivery_id].status == DeliveryStatus.IN_PROGRESS


def test_assign_requires_paid_order(service, storage):
    order = add_order(storage, add_user(storage).id, add_menu_item(storage).id, OrderStatus.PROCESSING)

    with pytest.raises(BusinessRuleError, match="оплаченный"):
        service.assign_courier(order.id, add_user(storage).id)


def test_assign_unknown_order(service, storage):
    with pytest.raises(NotFoundError, match="Заказ не найден"):
        service.assign_courier(999, add_user(storage).id)


def test_assign_blocked_courier(service, storage, paid_order):
    courier = add_user(storage, is_blocked=True)

    with pytest.raises(AccessDeniedError):
        service.assign_courier(paid_order.id, courier.id)


def test_courier_has_single_active_delivery(service, storage, paid_order):
    courier = add_user(storage)
    service.assign_courier(paid_order.id, courier.id)

    with pytest.raises(BusinessRuleError, match="активная доставка"):
        service.assign_courier(paid_order.id, courier.id)


def test_complete_delivery_marks_order_delivered(service, storage, paid_order):
    delivery = add_delivery(storage, paid_order.id, add_user(storage).id, DeliveryStatus.IN_PROGRESS)

    service.complete_delivery(delivery.id)

    assert storage.deliveries[delivery.id].status == DeliveryStatus.COMPLETED
    assert storage.orders[paid_order.id].status == OrderStatus.DELIVERED


@pytest.mark.parametrize(
    ("status", "message"),
    [(DeliveryStatus.COMPLETED, "уже завершена"), (DeliveryStatus.CANCELLED, "Отменённую")],
)
def test_complete_rejects_final_statuses(service, storage, paid_order, status, message):
    delivery = add_delivery(storage, paid_order.id, add_user(storage).id, status)

    with pytest.raises(BusinessRuleError, match=message):
        service.complete_delivery(delivery.id)
