from dataclasses import asdict
from decimal import Decimal
from time import monotonic
from typing import Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.domain.entities import User
from app.domain.exceptions import DomainError
from app.http_errors import to_http_exception
from app.modules.payments.contracts import GatewayResult, GatewayUnavailable, PaymentConflict
from app.modules.payments.dependencies import payment_service
from app.modules.payments.service import PaymentService
from app.modules.payments.telemetry import record_webhook
from app.core.observability import correlation_id_from_context

router = APIRouter()


def serialize(payment):
    return {**asdict(payment), 'amount': str(payment.amount)}


class Checkout(BaseModel):
    item_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=100)


class StartPayment(BaseModel):
    order_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2, allow_inf_nan=False)


class DemoResult(BaseModel):
    status: Literal['succeeded', 'canceled']


class NotificationObject(BaseModel):
    id: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9-]+$')


class Notification(BaseModel):
    type: Literal['notification']
    event: Literal['payment.succeeded', 'payment.canceled', 'refund.succeeded']
    object: NotificationObject


def call(action, *args):
    try:
        return action(*args)
    except DomainError as exc:
        raise to_http_exception(exc)
    except PaymentConflict as exc:
        raise HTTPException(409, str(exc))
    except GatewayUnavailable as exc:
        raise HTTPException(503, str(exc), headers={'Retry-After': '5'})


@router.get('/config')
def config():
    return {'provider': settings.PAYMENT_PROVIDER, 'test_mode': True}


@router.post('/checkout', status_code=201)
def checkout(
    payload: Checkout,
    request: Request,
    actor: User = Depends(get_current_user),
    service: PaymentService = Depends(payment_service),
):
    correlation_id = getattr(request.state, "correlation_id", None) or correlation_id_from_context()
    return call(service.create_order, actor, payload.item_id, payload.quantity, correlation_id)


@router.get('')
def list_payments(actor: User = Depends(get_current_user), service: PaymentService = Depends(payment_service)):
    return [serialize(p) for p in service.repository.list_for(actor)]


@router.post('')
def create(payload: StartPayment, idempotency_key: str = Header(min_length=8, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$'),
           actor: User = Depends(get_current_user), service: PaymentService = Depends(payment_service)):
    return serialize(call(service.create, actor, payload.order_id, idempotency_key, payload.amount))


@router.post('/webhook')
def webhook(payload: Notification, service: PaymentService = Depends(payment_service)):
    started = monotonic()
    payment = None
    status = 200
    try:
        if not settings.YOOKASSA_SHOP_ID or not settings.YOOKASSA_SECRET_KEY:
            raise HTTPException(404, 'Вебхуки отключены в демонстрационном режиме')
        action = service.webhook if payload.event.startswith('payment.') else service.refund_webhook
        payment = call(action, payload.object.id)
    except HTTPException as exc:
        status = exc.status_code
        raise
    except Exception:
        status = 500
        raise
    finally:
        record_webhook(payload.event, payload.object.id, payment, status, monotonic() - started)
    return {'received': True}


@router.get('/{payment_id}')
def get_payment(payment_id: str, actor: User = Depends(get_current_user), service: PaymentService = Depends(payment_service)):
    return serialize(call(service.get, payment_id, actor))


@router.post('/{payment_id}/refresh')
def refresh(payment_id: str, actor: User = Depends(get_current_user), service: PaymentService = Depends(payment_service)):
    payment = call(service.get, payment_id, actor)
    return serialize(call(service.sync, payment))


@router.post('/{payment_id}/demo')
def demo(payment_id: str, payload: DemoResult, actor: User = Depends(get_current_user),
         service: PaymentService = Depends(payment_service)):
    payment = call(service.get, payment_id, actor)
    if service.gateway.name != 'demo' or payment.provider != 'demo':
        raise HTTPException(404, 'Демонстрационная оплата отключена')
    result = GatewayResult(payment.id, payload.status, payment.amount, 'RUB', payment.order_id)
    return serialize(call(service._apply, payment, result))


@router.post('/orders/{order_id}/cancel')
def cancel(order_id: int, actor: User = Depends(get_current_user), service: PaymentService = Depends(payment_service)):
    call(service.repository.cancel, actor, order_id)
    return {'status': 'success'}
