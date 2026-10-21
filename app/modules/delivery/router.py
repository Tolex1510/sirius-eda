"""
Транспортный слой модуля доставки (круг 4: Frameworks & Drivers).
Доставкой занимается микросервис, роутер говорит с ним через DeliveryGateway.
"""
import itertools
import json
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_current_user, require_role
from app.dependencies import get_delivery_gateway
from app.domain.entities import Delivery, Role, User
from app.domain.exceptions import DomainError
from app.http_errors import to_http_exception
from app.modules.delivery.gateway import DeliveryGateway, DeliveryTimeoutError, DeliveryUnavailableError
from app.schemas import DeliveryAssign

router = APIRouter()

# Через сколько клиенту стоит повторить запрос, если сервис доставки лежит.
RETRY_AFTER_SECONDS = "5"


def call(action: Callable, *args, **kwargs):
    """Доменные ошибки в 4xx, недоступность сервиса доставки в 503 и 504."""
    try:
        return action(*args, **kwargs)
    except DomainError as e:
        raise to_http_exception(e)
    except DeliveryTimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DeliveryUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e), headers={"Retry-After": RETRY_AFTER_SECONDS})


@router.post("/assign")
def assign_courier(
    payload: DeliveryAssign,
    current_user: User = Depends(require_role(Role.COURIER, Role.ADMIN)),
    gateway: DeliveryGateway = Depends(get_delivery_gateway),
):
    delivery_id = call(gateway.assign_courier, payload.order_id, payload.courier_id, actor=current_user)
    return {"status": "success", "delivery_id": delivery_id}


@router.get("/my")
def my_deliveries(
    current_user: User = Depends(get_current_user),
    gateway: DeliveryGateway = Depends(get_delivery_gateway),
):
    return call(gateway.list_my_deliveries, current_user)


@router.get("/{delivery_id}")
def get_delivery(
    delivery_id: int,
    current_user: User = Depends(get_current_user),
    gateway: DeliveryGateway = Depends(get_delivery_gateway),
):
    return call(gateway.get_delivery, delivery_id, actor=current_user)


@router.patch("/{delivery_id}/pickup")
def pick_up(
    delivery_id: int,
    current_user: User = Depends(require_role(Role.COURIER, Role.ADMIN)),
    gateway: DeliveryGateway = Depends(get_delivery_gateway),
):
    return call(gateway.pick_up, delivery_id, actor=current_user)


@router.patch("/{delivery_id}/complete")
def complete_delivery(
    delivery_id: int,
    current_user: User = Depends(require_role(Role.COURIER, Role.ADMIN)),
    gateway: DeliveryGateway = Depends(get_delivery_gateway),
):
    call(gateway.complete_delivery, delivery_id, actor=current_user)
    return {"status": "success"}


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def status_event(delivery: Delivery) -> str:
    return sse("status", {"delivery_id": delivery.id, "courier_id": delivery.courier_id, "status": delivery.status})


@router.get("/{delivery_id}/track")
def track_delivery(
    delivery_id: int,
    current_user: User = Depends(get_current_user),
    gateway: DeliveryGateway = Depends(get_delivery_gateway),
):
    """
    Статусы доставки в реальном времени, Server-Sent Events. Браузер слушает их через EventSource,
    монолит пересылает то, что приходит из gRPC-стрима TrackDelivery.
    """
    updates = gateway.track(delivery_id, current_user)
    # Первое событие читаем до ответа: на чужую или несуществующую доставку вернётся 403 или 404, а не пустой поток.
    first = call(next, updates)

    def events():
        try:
            for delivery in itertools.chain([first], updates):
                yield status_event(delivery)
        except (DomainError, DeliveryUnavailableError) as e:
            yield sse("error", {"detail": str(e)})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
