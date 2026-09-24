"""
Транспортный слой модуля доставки (круг 4: Frameworks & Drivers).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.domain.exceptions import DomainError
from app.http_errors import to_http_exception
from app.modules.delivery.repository import SqlAlchemyDeliveryRepository
from app.modules.delivery.service import DeliveryService
from app.schemas import DeliveryAssign

router = APIRouter()


@router.post("/assign")
def assign_courier(payload: DeliveryAssign, db: Session = Depends(get_db)):
    service = DeliveryService(SqlAlchemyDeliveryRepository(db))

    try:
        delivery_id = service.assign_courier(
            order_id=payload.order_id,
            courier_id=payload.courier_id,
        )
    except DomainError as e:
        raise to_http_exception(e)

    return {"status": "success", "delivery_id": delivery_id}


@router.patch("/{delivery_id}/complete")
def complete_delivery(delivery_id: int, db: Session = Depends(get_db)):
    service = DeliveryService(SqlAlchemyDeliveryRepository(db))

    try:
        service.complete_delivery(delivery_id)
    except DomainError as e:
        raise to_http_exception(e)

    return {"status": "success"}
