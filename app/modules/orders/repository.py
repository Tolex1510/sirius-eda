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
    def save_order(self, user_id: int, item_id: int, quantity: int, new_balance: float) -> int:
        """
        Сохраняет заказ и новый баланс пользователя одной транзакцией.
        Возвращает идентификатор созданного заказа.
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

    def save_order(self, user_id: int, item_id: int, quantity: int, new_balance: float) -> int:
        user = self.db.query(UserModel).filter(UserModel.id == user_id).one()
        user.balance = new_balance
        new_order = OrderModel(
            user_id=user_id,
            item_id=item_id,
            quantity=quantity,
            status=OrderStatus.PROCESSING,
        )
        self.db.add(new_order)
        self.db.commit()
        self.db.refresh(new_order)
        return new_order.id


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

    def save_order(self, user_id: int, item_id: int, quantity: int, new_balance: float) -> int:
        order_id = self.storage.next_id("orders")
        self.storage.orders[order_id] = Order(
            id=order_id,
            user_id=user_id,
            item_id=item_id,
            quantity=quantity,
            status=OrderStatus.PROCESSING,
        )
        self.storage.users[user_id].balance = new_balance
        return order_id
