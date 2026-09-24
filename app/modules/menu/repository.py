"""
Инфраструктурный слой модуля меню (круг 3: Interface Adapters).
"""
from abc import ABC, abstractmethod
from dataclasses import replace

from sqlalchemy.orm import Session

from app.domain.entities import MenuItem
from app.models import MenuItem as MenuItemModel
from app.memory_storage import InMemoryStorage


class MenuRepository(ABC):
    """Контракт хранилища, от которого зависит MenuService."""

    @abstractmethod
    def get_by_id(self, item_id: int) -> MenuItem | None: ...

    @abstractmethod
    def get_by_name(self, name: str) -> MenuItem | None: ...

    @abstractmethod
    def create(self, name: str, price: float) -> MenuItem:
        """Создаёт доступное для заказа блюдо."""

    @abstractmethod
    def save(self, item: MenuItem) -> MenuItem: ...


class SqlAlchemyMenuRepository(MenuRepository):
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, item_id: int) -> MenuItem | None:
        item = self.db.query(MenuItemModel).filter(MenuItemModel.id == item_id).first()
        return item.to_entity() if item else None

    def get_by_name(self, name: str) -> MenuItem | None:
        item = self.db.query(MenuItemModel).filter(MenuItemModel.name == name).first()
        return item.to_entity() if item else None

    def create(self, name: str, price: float) -> MenuItem:
        new_item = MenuItemModel(name=name, price=price, is_available=True)
        self.db.add(new_item)
        self.db.commit()
        self.db.refresh(new_item)
        return new_item.to_entity()

    def save(self, item: MenuItem) -> MenuItem:
        row = self.db.query(MenuItemModel).filter(MenuItemModel.id == item.id).one()
        row.name = item.name
        row.price = item.price
        row.is_available = item.is_available
        self.db.commit()
        self.db.refresh(row)
        return row.to_entity()


class InMemoryMenuRepository(MenuRepository):
    """Хранит данные в памяти процесса. Используется в тестах и без СУБД."""

    def __init__(self, storage: InMemoryStorage):
        self.storage = storage

    def get_by_id(self, item_id: int) -> MenuItem | None:
        item = self.storage.menu_items.get(item_id)
        return replace(item) if item else None

    def get_by_name(self, name: str) -> MenuItem | None:
        for item in self.storage.menu_items.values():
            if item.name == name:
                return replace(item)
        return None

    def create(self, name: str, price: float) -> MenuItem:
        item = MenuItem(
            id=self.storage.next_id("menu_items"),
            name=name,
            price=price,
            is_available=True,
        )
        self.storage.menu_items[item.id] = item
        return replace(item)

    def save(self, item: MenuItem) -> MenuItem:
        self.storage.menu_items[item.id] = replace(item)
        return replace(item)
