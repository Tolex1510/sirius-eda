"""
Инфраструктурный слой модуля меню (круг 3: Interface Adapters).
"""
from abc import ABC, abstractmethod
from dataclasses import asdict, replace

from sqlalchemy.orm import Session

from app.core.cache import CacheAside
from app.database import short_transactions
from app.domain.entities import Category, CategoryMenu, MenuItem
from app.memory_storage import InMemoryStorage
from app.models import Category as CategoryModel
from app.models import MenuItem as MenuItemModel


class MenuRepository(ABC):
    """Контракт хранилища, от которого зависит MenuService."""

    @abstractmethod
    def get_by_id(self, item_id: int) -> MenuItem | None: ...

    @abstractmethod
    def get_by_name(self, name: str) -> MenuItem | None: ...

    @abstractmethod
    def list_all(self) -> list[MenuItem]:
        """Всё меню: по разделам, внутри раздела по названию."""

    @abstractmethod
    def create(self, name: str, price: float, category_id: int | None = None) -> MenuItem:
        """Создаёт доступное для заказа блюдо."""

    @abstractmethod
    def save(self, item: MenuItem) -> MenuItem: ...

    @abstractmethod
    def get_category(self, category_id: int) -> Category | None: ...

    @abstractmethod
    def get_category_by_name(self, name: str) -> Category | None: ...

    @abstractmethod
    def list_categories(self) -> list[Category]: ...

    @abstractmethod
    def create_category(self, name: str) -> Category: ...

    @abstractmethod
    def get_category_menu(self, category_id: int) -> CategoryMenu | None: ...


@short_transactions
class SqlAlchemyMenuRepository(MenuRepository):
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, item_id: int) -> MenuItem | None:
        item = self.db.query(MenuItemModel).filter(MenuItemModel.id == item_id).first()
        return item.to_entity() if item else None

    def get_by_name(self, name: str) -> MenuItem | None:
        item = self.db.query(MenuItemModel).filter(MenuItemModel.name == name).first()
        return item.to_entity() if item else None

    def list_all(self) -> list[MenuItem]:
        rows = (
            self.db.query(MenuItemModel)
            .outerjoin(CategoryModel, CategoryModel.id == MenuItemModel.category_id)
            .order_by(CategoryModel.name.asc().nulls_last(), MenuItemModel.name, MenuItemModel.id)
        )
        return [row.to_entity() for row in rows]

    def create(self, name: str, price: float, category_id: int | None = None) -> MenuItem:
        new_item = MenuItemModel(name=name, price=price, is_available=True, category_id=category_id)
        self.db.add(new_item)
        self.db.commit()
        self.db.refresh(new_item)
        return new_item.to_entity()

    def save(self, item: MenuItem) -> MenuItem:
        row = self.db.query(MenuItemModel).filter(MenuItemModel.id == item.id).one()
        row.name = item.name
        row.price = item.price
        row.is_available = item.is_available
        row.category_id = item.category_id
        self.db.commit()
        self.db.refresh(row)
        return row.to_entity()

    def get_category(self, category_id: int) -> Category | None:
        row = self.db.query(CategoryModel).filter(CategoryModel.id == category_id).first()
        return row.to_entity() if row else None

    def get_category_by_name(self, name: str) -> Category | None:
        row = self.db.query(CategoryModel).filter(CategoryModel.name == name).first()
        return row.to_entity() if row else None

    def list_categories(self) -> list[Category]:
        return [row.to_entity() for row in self.db.query(CategoryModel).order_by(CategoryModel.name)]

    def create_category(self, name: str) -> Category:
        row = CategoryModel(name=name)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row.to_entity()

    def get_category_menu(self, category_id: int) -> CategoryMenu | None:
        category = self.get_category(category_id)
        if not category:
            return None
        rows = (
            self.db.query(MenuItemModel)
            .filter(MenuItemModel.category_id == category_id)
            .order_by(MenuItemModel.name, MenuItemModel.id)
        )
        return CategoryMenu(id=category.id, name=category.name, items=[row.to_entity() for row in rows])


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

    def list_all(self) -> list[MenuItem]:
        def sort_key(item: MenuItem):
            category = self.storage.categories.get(item.category_id)
            return (category is None, category.name if category else "", item.name, item.id)

        return [replace(item) for item in sorted(self.storage.menu_items.values(), key=sort_key)]

    def create(self, name: str, price: float, category_id: int | None = None) -> MenuItem:
        item = MenuItem(
            id=self.storage.next_id("menu_items"),
            name=name,
            price=price,
            is_available=True,
            category_id=category_id,
        )
        self.storage.menu_items[item.id] = item
        return replace(item)

    def save(self, item: MenuItem) -> MenuItem:
        self.storage.menu_items[item.id] = replace(item)
        return replace(item)

    def get_category(self, category_id: int) -> Category | None:
        category = self.storage.categories.get(category_id)
        return replace(category) if category else None

    def get_category_by_name(self, name: str) -> Category | None:
        for category in self.storage.categories.values():
            if category.name == name:
                return replace(category)
        return None

    def list_categories(self) -> list[Category]:
        return [replace(c) for c in sorted(self.storage.categories.values(), key=lambda c: c.name)]

    def create_category(self, name: str) -> Category:
        category = Category(id=self.storage.next_id("categories"), name=name)
        self.storage.categories[category.id] = category
        return replace(category)

    def get_category_menu(self, category_id: int) -> CategoryMenu | None:
        category = self.storage.categories.get(category_id)
        if not category:
            return None
        items = sorted(
            (replace(i) for i in self.storage.menu_items.values() if i.category_id == category_id),
            key=lambda i: (i.name, i.id),
        )
        return CategoryMenu(id=category.id, name=category.name, items=items)


MENU_ALL_KEY = "menu:all"
MENU_ALL_TTL = 300
CATEGORY_TTL = 600


def category_key(category_id: int) -> str:
    return f"menu:category:{category_id}"


class CachedMenuRepository(MenuRepository):
    """
    Cache-Aside для чтения меню. Декоратор над любым MenuRepository: чтение всего меню
    и разделов идёт через Redis, остальное передаётся в исходный репозиторий без изменений.

    Инвалидация событийная: после каждой записи в меню сбрасываются затронутые ключи.
    TTL страхует от того, что сброс не прошёл или данные поменяли в БД в обход приложения.
    MenuService про кеш не знает и работает с этим классом как с обычным репозиторием.
    """

    def __init__(self, inner: MenuRepository, cache: CacheAside):
        self.inner = inner
        self.cache = cache

    def list_all(self) -> list[MenuItem]:
        data = self.cache.get_or_load(
            MENU_ALL_KEY,
            MENU_ALL_TTL,
            lambda: [asdict(item) for item in self.inner.list_all()],
        )
        return [MenuItem(**item) for item in data]

    def get_category_menu(self, category_id: int) -> CategoryMenu | None:
        def load():
            menu = self.inner.get_category_menu(category_id)
            return asdict(menu) if menu else None

        data = self.cache.get_or_load(category_key(category_id), CATEGORY_TTL, load)
        if data is None:
            return None
        return CategoryMenu(id=data["id"], name=data["name"], items=[MenuItem(**i) for i in data["items"]])

    def warm_up(self) -> None:
        """Заполняет кеш при старте, чтобы первые запросы после деплоя не шли в БД."""
        self.cache.put(MENU_ALL_KEY, MENU_ALL_TTL, [asdict(item) for item in self.inner.list_all()])
        for category in self.inner.list_categories():
            self.cache.put(category_key(category.id), CATEGORY_TTL, asdict(self.inner.get_category_menu(category.id)))

    def create(self, name: str, price: float, category_id: int | None = None) -> MenuItem:
        item = self.inner.create(name, price, category_id)
        self._invalidate(item.category_id)
        return item

    def save(self, item: MenuItem) -> MenuItem:
        before = self.inner.get_by_id(item.id)
        saved = self.inner.save(item)
        # При переносе блюда устаревают оба раздела: старый и новый.
        self._invalidate(saved.category_id, before.category_id if before else None)
        return saved

    def _invalidate(self, *category_ids: int | None) -> None:
        keys = [MENU_ALL_KEY] + [category_key(c) for c in set(category_ids) if c is not None]
        self.cache.invalidate(*keys)

    # Остальные операции кешировать незачем: они редкие или нужны свежими.

    def get_by_id(self, item_id: int) -> MenuItem | None:
        return self.inner.get_by_id(item_id)

    def get_by_name(self, name: str) -> MenuItem | None:
        return self.inner.get_by_name(name)

    def get_category(self, category_id: int) -> Category | None:
        return self.inner.get_category(category_id)

    def get_category_by_name(self, name: str) -> Category | None:
        return self.inner.get_category_by_name(name)

    def list_categories(self) -> list[Category]:
        return self.inner.list_categories()

    def create_category(self, name: str) -> Category:
        category = self.inner.create_category(name)
        # Для новой категории мог закешироваться промах (None), если её id запрашивали раньше.
        self.cache.invalidate(category_key(category.id))
        return category
