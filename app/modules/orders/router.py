"""
Транспортный слой модуля заказов (круг 4: Frameworks & Drivers).
Принимает HTTP-запрос, выполняет техническую валидацию,
вызывает сервис и переводит исключения в HTTP-статусы.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.dependencies import get_current_user, require_role
from app.dependencies import get_order_notifier, get_order_repository
from app.domain.entities import Role, User
from app.domain.exceptions import DomainError
from app.http_errors import to_http_exception
from app.modules.orders.notifier import OrderNotifier
from app.modules.orders.repository import OrderRepository
from app.modules.orders.service import OrderService, OrderStatsService
from app.core.observability import correlation_id_from_context
from app.schemas import OrderCreate

router = APIRouter()
# Отдельный роутер, чтобы путь был /kitchen/orders, а не /orders/kitchen/orders.
kitchen_router = APIRouter()


def get_order_service(
    repository: OrderRepository = Depends(get_order_repository),
    notifier: OrderNotifier = Depends(get_order_notifier),
) -> OrderService:
    """Сборка слоёв: конкретные реализации внедряются в сервис через конструктор."""
    return OrderService(repository, notifier)


@router.post("/create")
def create_order(
    request: Request,
    payload: OrderCreate,
    current_user: User = Depends(require_role(Role.STUDENT)),
    service: OrderService = Depends(get_order_service),
):
    if payload.quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Количество должно быть больше нуля",
        )

    try:
        order_id = service.create_order(
            user_id=current_user.id,
            item_id=payload.item_id,
            quantity=payload.quantity,
            correlation_id=getattr(request.state, "correlation_id", None) or correlation_id_from_context(),
        )
    except DomainError as e:
        raise to_http_exception(e)

    return {"status": "success", "order_id": order_id}


@router.get("/my")
def my_orders(
    current_user: User = Depends(get_current_user),
    service: OrderService = Depends(get_order_service),
):
    return service.list_user_orders(current_user)


@router.get("/stats")
def order_stats(
    days: int = Query(default=7, ge=1, le=90),
    _: User = Depends(require_role(Role.ADMIN)),
    repository: OrderRepository = Depends(get_order_repository),
):
    """Сводка по дням. Пересчитывается раз в минуту задачей Celery Beat."""
    return OrderStatsService(repository).recent(days)


@router.post("/{order_id}/cancel")
def cancel_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    service: OrderService = Depends(get_order_service),
):
    try:
        service.cancel_order(order_id, actor=current_user)
    except DomainError as e:
        raise to_http_exception(e)

    return {"status": "success"}


@router.post("/{order_id}/pay")
def pay_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    service: OrderService = Depends(get_order_service),
):
    try:
        order = service.pay_order(order_id, actor=current_user)
    except DomainError as e:
        raise to_http_exception(e)

    return {"status": "success", "order_id": order.id, "order_status": order.status}


@kitchen_router.get("/orders")
def kitchen_orders(
    _: User = Depends(require_role(Role.COOK, Role.ADMIN)),
    service: OrderService = Depends(get_order_service),
):
    return service.get_kitchen_orders()
