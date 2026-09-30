"""
Транспортный слой модуля доставки (круг 4: Frameworks & Drivers).
"""
from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user, require_role
from app.dependencies import get_delivery_repository
from app.domain.entities import Role, User
from app.domain.exceptions import DomainError
from app.http_errors import to_http_exception
from app.modules.delivery.repository import DeliveryRepository
from app.modules.delivery.service import DeliveryService
from app.schemas import DeliveryAssign

router = APIRouter()


def get_delivery_service(repository: DeliveryRepository = Depends(get_delivery_repository)) -> DeliveryService:
    """Сборка слоёв: конкретный репозиторий внедряется в сервис через конструктор."""
    return DeliveryService(repository)


@router.post("/assign")
def assign_courier(
    payload: DeliveryAssign,
    current_user: User = Depends(require_role(Role.COURIER, Role.ADMIN)),
    service: DeliveryService = Depends(get_delivery_service),
):
    try:
        delivery_id = service.assign_courier(
            order_id=payload.order_id,
            courier_id=payload.courier_id,
            actor=current_user,
        )
    except DomainError as e:
        raise to_http_exception(e)

    return {"status": "success", "delivery_id": delivery_id}


@router.get("/my")
def my_deliveries(
    current_user: User = Depends(get_current_user),
    service: DeliveryService = Depends(get_delivery_service),
):
    return service.list_my_deliveries(current_user)


@router.get("/{delivery_id}")
def get_delivery(
    delivery_id: int,
    current_user: User = Depends(get_current_user),
    service: DeliveryService = Depends(get_delivery_service),
):
    try:
        return service.get_delivery(delivery_id, actor=current_user)
    except DomainError as e:
        raise to_http_exception(e)


@router.patch("/{delivery_id}/complete")
def complete_delivery(
    delivery_id: int,
    current_user: User = Depends(require_role(Role.COURIER, Role.ADMIN)),
    service: DeliveryService = Depends(get_delivery_service),
):
    try:
        service.complete_delivery(delivery_id, actor=current_user)
    except DomainError as e:
        raise to_http_exception(e)

    return {"status": "success"}
