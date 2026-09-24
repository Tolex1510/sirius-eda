"""
Транспортный слой модуля доставки (круг 4: Frameworks & Drivers).
"""
from fastapi import APIRouter, Depends

from app.dependencies import get_delivery_repository
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
def assign_courier(payload: DeliveryAssign, service: DeliveryService = Depends(get_delivery_service)):
    try:
        delivery_id = service.assign_courier(
            order_id=payload.order_id,
            courier_id=payload.courier_id,
        )
    except DomainError as e:
        raise to_http_exception(e)

    return {"status": "success", "delivery_id": delivery_id}


@router.patch("/{delivery_id}/complete")
def complete_delivery(delivery_id: int, service: DeliveryService = Depends(get_delivery_service)):
    try:
        service.complete_delivery(delivery_id)
    except DomainError as e:
        raise to_http_exception(e)

    return {"status": "success"}
