"""
Инфраструктурный слой модуля заказов (круг 3: Interface Adapters).
Единственное место модуля, которое знает о SQLAlchemy и таблицах БД.
"""
from abc import ABC, abstractmethod
from dataclasses import replace

from sqlalchemy.orm import Session

from app.domain.entities import MenuItem, Order, OrderStatus, User
from app.models import MenuItem as MenuItemModel
from app.models import Order as OrderModel
from app.models import User as UserModel
from app.memory_storage import InMemoryStorage


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
