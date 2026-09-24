"""
Транспортный слой модуля заказов (круг 4: Frameworks & Drivers).
Принимает HTTP-запрос, выполняет техническую валидацию,
вызывает сервис и переводит исключения в HTTP-статусы.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.domain.exceptions import DomainError
from app.http_errors import to_http_exception
from app.modules.orders.repository import SqlAlchemyOrderRepository
from app.modules.orders.service import OrderService
from app.schemas import OrderCreate

router = APIRouter()


@router.post("/create")
def create_order(payload: OrderCreate, db: Session = Depends(get_db)):
    if payload.quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Количество должно быть больше нуля",
        )

    service = OrderService(SqlAlchemyOrderRepository(db))

    try:
        order_id = service.create_order(
            user_id=payload.user_id,
            item_id=payload.item_id,
            quantity=payload.quantity,
        )
    except DomainError as e:
        raise to_http_exception(e)

    return {"status": "success", "order_id": order_id}
