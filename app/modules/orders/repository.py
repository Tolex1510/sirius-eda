"""
Инфраструктурный слой модуля заказов (круг 3: Interface Adapters).
Единственное место модуля, которое знает о SQLAlchemy и таблицах БД.
"""
from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import short_transactions
from app.domain.entities import DailyOrderStats, MenuItem, Order, OrderStatus, User
from app.domain.events import OrderCancelled, OrderPaid, Receipt
from app.domain.exceptions import AlreadyProcessedError
from app.memory_storage import InMemoryStorage
from app.models import MenuItem as MenuItemModel
from app.models import Order as OrderModel
from app.models import OrderStats as OrderStatsModel
from app.models import User as UserModel
from app.outbox import add_receipt, add_to_outbox, commit_once, has_receipt


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


class OrderRepository(ABC):
    """Контракт хранилища, от которого зависит OrderService."""

    @abstractmethod
    def get_user_by_id(self, user_id: int) -> User | None: ...

    @abstractmethod
    def get_menu_item_by_id(self, item_id: int) -> MenuItem | None: ...

    @abstractmethod
    def get_order(self, order_id: int) -> Order | None: ...

    @abstractmethod
    def list_orders_by_user(self, user_id: int) -> list[Order]: ...

    @abstractmethod
    def list_orders_by_status(self, statuses: tuple[str, ...]) -> list[Order]: ...

    @abstractmethod
    def save_order(self, user_id: int, item_id: int, quantity: int, total_cost: float, new_balance: float) -> int:
        """
        Сохраняет заказ и новый баланс пользователя одной транзакцией.
        Возвращает идентификатор созданного заказа.
        """

    @abstractmethod
    def cancel_and_refund(self, order: Order) -> bool:
        """
        Переводит заказ из processing в cancelled и возвращает total_cost на баланс
        одной транзакцией. False, если заказ уже не в processing.
        """

    @abstractmethod
    def mark_paid(self, order: Order, event: OrderPaid) -> bool:
        """
        Переводит заказ из processing в paid и кладёт событие в outbox одной транзакцией.
        False, если заказ уже не в processing.
        """

    @abstractmethod
    def is_processed(self, receipt: Receipt) -> bool: ...

    @abstractmethod
    def cancel_paid_and_refund(self, order: Order, event: OrderCancelled, receipt: Receipt) -> bool:
        """
        Компенсация саги одной транзакцией: paid в cancelled, возврат total_cost, событие в outbox
        и отметка об обработке. False, если заказ уже не в paid: тогда пишется только отметка.
        Повтор отметки: AlreadyProcessedError.
        """

    @abstractmethod
    def refresh_daily_stats(self, day: date) -> DailyOrderStats:
        """Пересчитывает и сохраняет сводку за день."""

    @abstractmethod
    def list_daily_stats(self, days: int) -> list[DailyOrderStats]:
        """Последние сводки, новые первыми."""


@short_transactions
class SqlAlchemyOrderRepository(OrderRepository):
    def __init__(self, db: Session):
        self.db = db

    def get_user_by_id(self, user_id: int) -> User | None:
        user = self.db.query(UserModel).filter(UserModel.id == user_id).first()
        return user.to_entity() if user else None

    def get_menu_item_by_id(self, item_id: int) -> MenuItem | None:
        item = self.db.query(MenuItemModel).filter(MenuItemModel.id == item_id).first()
        return item.to_entity() if item else None

    def get_order(self, order_id: int) -> Order | None:
        order = self.db.query(OrderModel).filter(OrderModel.id == order_id).first()
        return order.to_entity() if order else None

    def list_orders_by_user(self, user_id: int) -> list[Order]:
        rows = self.db.query(OrderModel).filter(OrderModel.user_id == user_id).order_by(OrderModel.id)
        return [row.to_entity() for row in rows]

    def list_orders_by_status(self, statuses: tuple[str, ...]) -> list[Order]:
        rows = self.db.query(OrderModel).filter(OrderModel.status.in_(statuses)).order_by(OrderModel.id)
        return [row.to_entity() for row in rows]

    def save_order(self, user_id: int, item_id: int, quantity: int, total_cost: float, new_balance: float) -> int:
        user = self.db.query(UserModel).filter(UserModel.id == user_id).one()
        user.balance = new_balance
        new_order = OrderModel(
            user_id=user_id,
            item_id=item_id,
            quantity=quantity,
            status=OrderStatus.PROCESSING,
            total_cost=total_cost,
        )
        self.db.add(new_order)
        self.db.commit()
        self.db.refresh(new_order)
        return new_order.id

    def cancel_and_refund(self, order: Order) -> bool:
        # Условие на статус в самом UPDATE: две параллельные отмены не вернут деньги дважды.
        updated = (
            self.db.query(OrderModel)
            .filter(OrderModel.id == order.id, OrderModel.status == OrderStatus.PROCESSING)
            .update({"status": OrderStatus.CANCELLED})
        )
        if updated != 1:
            self.db.rollback()
            return False
        self.db.query(UserModel).filter(UserModel.id == order.user_id).update(
            {"balance": UserModel.balance + order.total_cost}
        )
        self.db.commit()
        return True

    def mark_paid(self, order: Order, event: OrderPaid) -> bool:
        updated = (
            self.db.query(OrderModel)
            .filter(OrderModel.id == order.id, OrderModel.status == OrderStatus.PROCESSING)
            .update({"status": OrderStatus.PAID})
        )
        if updated != 1:
            self.db.rollback()
            return False
        add_to_outbox(self.db, event)
        self.db.commit()
        return True

    def is_processed(self, receipt: Receipt) -> bool:
        return has_receipt(self.db, receipt)

    def cancel_paid_and_refund(self, order: Order, event: OrderCancelled, receipt: Receipt) -> bool:
        updated = (
            self.db.query(OrderModel)
            .filter(OrderModel.id == order.id, OrderModel.status == OrderStatus.PAID)
            .update({"status": OrderStatus.CANCELLED})
        )
        if updated == 1:
            self.db.query(UserModel).filter(UserModel.id == order.user_id).update(
                {"balance": UserModel.balance + order.total_cost}
            )
            add_to_outbox(self.db, event)
        add_receipt(self.db, receipt)
        commit_once(self.db)
        return updated == 1

    def refresh_daily_stats(self, day: date) -> DailyOrderStats:
        start, end = day_bounds(day)
        orders, revenue = (
            self.db.query(func.count(OrderModel.id), func.coalesce(func.sum(OrderModel.total_cost), 0.0))
            .filter(
                OrderModel.created_at >= start,
                OrderModel.created_at < end,
                OrderModel.status != OrderStatus.CANCELLED,
            )
            .one()
        )
        stats = self.db.merge(OrderStatsModel(day=day, orders=orders, revenue=revenue, updated_at=datetime.now(UTC)))
        self.db.commit()
        return stats.to_entity()

    def list_daily_stats(self, days: int) -> list[DailyOrderStats]:
        rows = self.db.query(OrderStatsModel).order_by(OrderStatsModel.day.desc()).limit(days)
        return [row.to_entity() for row in rows]


class InMemoryOrderRepository(OrderRepository):
    """Хранит данные в памяти процесса. Используется в тестах и без СУБД."""

    def __init__(self, storage: InMemoryStorage):
        self.storage = storage

    def get_user_by_id(self, user_id: int) -> User | None:
        user = self.storage.users.get(user_id)
        return replace(user) if user else None

    def get_menu_item_by_id(self, item_id: int) -> MenuItem | None:
        item = self.storage.menu_items.get(item_id)
        return replace(item) if item else None

    def get_order(self, order_id: int) -> Order | None:
        order = self.storage.orders.get(order_id)
        return replace(order) if order else None

    def list_orders_by_user(self, user_id: int) -> list[Order]:
        return [replace(o) for o in self.storage.orders.values() if o.user_id == user_id]

    def list_orders_by_status(self, statuses: tuple[str, ...]) -> list[Order]:
        return [replace(o) for o in self.storage.orders.values() if o.status in statuses]

    def save_order(self, user_id: int, item_id: int, quantity: int, total_cost: float, new_balance: float) -> int:
        order_id = self.storage.next_id("orders")
        self.storage.orders[order_id] = Order(
            id=order_id,
            user_id=user_id,
            item_id=item_id,
            quantity=quantity,
            status=OrderStatus.PROCESSING,
            total_cost=total_cost,
            created_at=datetime.now(UTC),
        )
        self.storage.users[user_id].balance = new_balance
        return order_id

    def cancel_and_refund(self, order: Order) -> bool:
        stored = self.storage.orders[order.id]
        if stored.status != OrderStatus.PROCESSING:
            return False
        stored.status = OrderStatus.CANCELLED
        self.storage.users[order.user_id].balance += order.total_cost
        return True

    def mark_paid(self, order: Order, event: OrderPaid) -> bool:
        stored = self.storage.orders[order.id]
        if stored.status != OrderStatus.PROCESSING:
            return False
        stored.status = OrderStatus.PAID
        self.storage.outbox.append(event)
        return True

    def is_processed(self, receipt: Receipt) -> bool:
        return receipt in self.storage.receipts

    def cancel_paid_and_refund(self, order: Order, event: OrderCancelled, receipt: Receipt) -> bool:
        if receipt in self.storage.receipts:
            raise AlreadyProcessedError("Событие уже обработано")
        self.storage.receipts.add(receipt)
        stored = self.storage.orders[order.id]
        if stored.status != OrderStatus.PAID:
            return False
        stored.status = OrderStatus.CANCELLED
        self.storage.users[order.user_id].balance += order.total_cost
        self.storage.outbox.append(event)
        return True

    def refresh_daily_stats(self, day: date) -> DailyOrderStats:
        start, end = day_bounds(day)
        counted = [
            o for o in self.storage.orders.values()
            if o.created_at and start <= o.created_at < end and o.status != OrderStatus.CANCELLED
        ]
        stats = DailyOrderStats(
            day=day,
            orders=len(counted),
            revenue=sum(o.total_cost for o in counted),
            updated_at=datetime.now(UTC),
        )
        self.storage.order_stats[day] = stats
        return replace(stats)

    def list_daily_stats(self, days: int) -> list[DailyOrderStats]:
        return [replace(s) for _, s in sorted(self.storage.order_stats.items(), reverse=True)[:days]]
