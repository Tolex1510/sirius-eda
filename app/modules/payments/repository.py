"""Атомарные переходы платежа, заказа и outbox. Сетевых вызовов здесь нет."""
from datetime import UTC, datetime
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.domain.entities import Role
from app.domain.events import OrderCancelled, OrderPaid
from app.domain.exceptions import AccessDeniedError, AlreadyProcessedError, BusinessRuleError, NotFoundError
from app.domain.money import money
from app.models import Delivery, MenuItem, Order, Payment as Row
from app.modules.payments.contracts import Payment, PaymentConflict, PaymentRepository
from app.outbox import add_receipt, add_to_outbox, commit_once, has_receipt


def entity(row):
    return Payment(row.id, row.order_id, row.user_id, money(row.amount), row.provider, row.status,
                   row.idempotency_key, row.gateway_id, row.confirmation_url, row.refund_status, row.refund_id,
                   row.created_at, row.refund_started_at, row.review_required, row.cancellation_reason)


class SqlPaymentRepository(PaymentRepository):
    def __init__(self, session_factory):
        self.sessions = session_factory

    def _order(self, db, order_id, actor=None):
        order = db.scalar(select(Order).where(Order.id == order_id).with_for_update())
        if not order:
            raise NotFoundError('Заказ не найден')
        if actor and actor.id != order.user_id and actor.role != Role.ADMIN:
            raise AccessDeniedError('Нет доступа к чужому заказу')
        return order

    def create_order(self, actor, item_id, quantity, correlation_id=None):
        with self.sessions.begin() as db:
            item = db.get(MenuItem, item_id)
            if not item or not item.is_available:
                raise BusinessRuleError('Блюдо недоступно')
            order = Order(user_id=actor.id, item_id=item_id, quantity=quantity, status='processing',
                          total_cost=money(item.price) * quantity, payment_source='gateway',
                          correlation_id=correlation_id)
            db.add(order)
            db.flush()
            return order.to_entity()

    def reserve(self, actor, order_id, key, provider, amount):
        try:
            with self.sessions.begin() as db:
                order = self._order(db, order_id, actor)
                if money(amount) != money(order.total_cost):
                    raise PaymentConflict('Сумма платежа не совпадает с суммой заказа')
                existing_key = db.scalar(select(Row).where(Row.user_id == actor.id, Row.idempotency_key == key))
                if existing_key and existing_key.order_id != order_id:
                    raise PaymentConflict('Ключ уже использован для другого заказа')
                existing = db.scalar(select(Row).where(Row.order_id == order_id))
                if existing:
                    if existing.user_id != actor.id:
                        raise AccessDeniedError('Оплатить может только владелец заказа')
                    if existing.idempotency_key != key:
                        raise PaymentConflict('Платёж уже создан: используйте его сохранённый ключ')
                    return entity(existing)
                if order.user_id != actor.id or order.payment_source != 'gateway' or order.status != 'processing':
                    raise BusinessRuleError('Заказ недоступен для внешней оплаты')
                row = Row(id=str(uuid4()), order_id=order_id, user_id=actor.id, amount=order.total_cost,
                          provider=provider, status='creating', idempotency_key=key)
                db.add(row)
                db.flush()
                return entity(row)
        except IntegrityError as exc:
            raise PaymentConflict('Параллельный запрос уже создал платёж; повторите с прежним ключом') from exc

    def get(self, payment_id):
        with self.sessions() as db:
            row = db.get(Row, payment_id)
            if not row:
                raise NotFoundError('Платёж не найден')
            return entity(row)

    def get_by_gateway(self, gateway_id):
        with self.sessions() as db:
            row = db.scalar(select(Row).where(Row.gateway_id == gateway_id))
            return entity(row) if row else None

    def get_by_refund(self, refund_id):
        with self.sessions() as db:
            row = db.scalar(select(Row).where(Row.refund_id == refund_id))
            return entity(row) if row else None

    def apply(self, payment_id, result):
        with self.sessions.begin() as db:
            row = db.get(Row, payment_id)
            if not row:
                raise NotFoundError('Платёж не найден')
            # Все переходы блокируют сначала заказ, затем платёж.
            order = self._order(db, row.order_id)
            db.refresh(row, with_for_update=True)
            if row.gateway_id and row.gateway_id != result.id:
                raise PaymentConflict('Идентификатор провайдера изменился')
            if result.status not in ('pending', 'waiting_for_capture', 'succeeded', 'canceled'):
                raise BusinessRuleError('Неизвестный статус провайдера')
            row.gateway_id = result.id
            row.confirmation_url = result.confirmation_url or row.confirmation_url
            row.updated_at = datetime.now(UTC)
            row.review_required = False
            if row.status not in ('succeeded', 'canceled'):
                row.status = result.status
                row.cancellation_reason = result.cancellation_reason
                if result.status == 'succeeded':
                    if order.status == 'processing':
                        order.status = 'paid'
                        add_to_outbox(db, OrderPaid(
                            order_id=order.id, customer_id=order.user_id, amount=float(row.amount),
                            correlation_id=order.correlation_id,
                        ))
                    elif order.status == 'cancelled':
                        # Первое OrderCancelled могло прийти до подтверждения оплаты.
                        # Повторный факт отмены инициирует компенсацию уже подтверждённого платежа.
                        add_to_outbox(db, OrderCancelled(
                            order_id=order.id, customer_id=order.user_id, refund=float(row.amount),
                            reason='Оплата подтверждена после отмены заказа', correlation_id=order.correlation_id,
                        ))
            return entity(row)

    def cancel(self, actor, order_id):
        with self.sessions.begin() as db:
            order = self._order(db, order_id, actor)
            if order.payment_source != 'gateway':
                raise BusinessRuleError('Используйте отмену заказа с внутреннего баланса')
            if order.status == 'cancelled':
                return
            if order.status not in ('processing', 'paid'):
                raise BusinessRuleError('Завершённый заказ нельзя отменить')
            delivery = db.scalar(select(Delivery).where(Delivery.order_id == order_id, Delivery.status != "cancelled").with_for_update())
            if delivery and delivery.status not in ('cancelled', 'in_progress', 'pending'):
                raise BusinessRuleError('Заказ уже в пути: отмена недоступна')
            if delivery:
                delivery.status = 'cancelled'
            order.status = 'cancelled'
            add_to_outbox(db, OrderCancelled(order_id=order.id, customer_id=order.user_id,
                                             refund=float(order.total_cost), reason='Отмена клиентом'))

    def request_refund(self, event, receipt):
        with self.sessions() as db:
            order = self._order(db, event.order_id)
            if has_receipt(db, receipt):
                raise AlreadyProcessedError('Событие отмены уже обработано')
            if order.status != 'cancelled' or order.user_id != event.customer_id:
                raise BusinessRuleError('Событие не соответствует отменённому заказу')
            row = db.scalar(select(Row).where(Row.order_id == order.id).with_for_update())
            requested = None
            if row and row.status == 'succeeded':
                if money(event.refund) != money(row.amount):
                    raise BusinessRuleError('Сумма компенсации не совпадает с платежом')
                if row.refund_status is None:
                    row.refund_status = 'pending'
                    row.refund_started_at = datetime.now(UTC)
                    requested = entity(row)
            add_receipt(db, receipt)
            commit_once(db)
            return requested

    def refund_result(self, payment_id, refund_id, status):
        with self.sessions.begin() as db:
            row = db.scalar(select(Row).where(Row.id == payment_id).with_for_update())
            if row.refund_status != 'succeeded':
                row.refund_id = refund_id
                row.refund_status = status
                row.updated_at = datetime.now(UTC)

    def pending(self):
        with self.sessions() as db:
            rows = db.scalars(select(Row).where(
                Row.review_required.is_(False),
                (Row.status.in_(['creating', 'pending', 'waiting_for_capture'])) | (Row.refund_status == 'pending')
            ).order_by(Row.updated_at).limit(100))
            return [entity(r) for r in rows]

    def mark_review(self, payment_id):
        with self.sessions.begin() as db:
            db.query(Row).filter(Row.id == payment_id).update({"review_required": True})

    def list_for(self, actor):
        with self.sessions() as db:
            return [entity(r) for r in db.scalars(select(Row).where(Row.user_id == actor.id).order_by(Row.created_at.desc()))]
