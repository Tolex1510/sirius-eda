"""
Слой бизнес-логики модуля меню (круги 1 и 2: Entities и Use Cases).
Импорты fastapi, sqlalchemy и redis здесь запрещены: сервис не знает,
пришли данные из PostgreSQL или из кеша.
"""
from app.domain.entities import Category, CategoryMenu, MenuItem
from app.domain.exceptions import BusinessRuleError, NotFoundError
from app.modules.menu.repository import MenuRepository


class MenuService:
    def __init__(self, repository: MenuRepository):
        self.repository = repository

    def list_items(self) -> list[MenuItem]:
        return [item for item in self.repository.list_all() if not item.is_archived]

    def get_item(self, item_id: int) -> MenuItem:
        item = self.repository.get_by_id(item_id)
        if not item:
            raise NotFoundError("Блюдо не найдено")
        return item

    def list_categories(self) -> list[Category]:
        return self.repository.list_categories()

    def get_category_menu(self, category_id: int) -> CategoryMenu:
        menu = self.repository.get_category_menu(category_id)
        if not menu:
            raise NotFoundError("Категория не найдена")
        menu.items = [item for item in menu.items if not item.is_archived]
        return menu

    def create_category(self, name: str) -> Category:
        if self.repository.get_category_by_name(name):
            raise BusinessRuleError("Категория с таким названием уже существует")
        return self.repository.create_category(name)

    def create_item(self, name: str, price: float, category_id: int | None = None) -> MenuItem:
        if self.repository.get_by_name(name):
            raise BusinessRuleError("Блюдо с таким названием уже существует")
        self._ensure_category_exists(category_id)
        return self.repository.create(name=name, price=price, category_id=category_id)

    def update_item(
        self,
        item_id: int,
        name: str | None = None,
        price: float | None = None,
        is_available: bool | None = None,
        category_id: int | None = None,
    ) -> MenuItem:
        item = self.repository.get_by_id(item_id)
        if not item:
            raise NotFoundError("Блюдо не найдено")

        self._ensure_category_exists(category_id)

        if name is not None:
            item.name = name
        if price is not None:
            item.price = price
        if is_available is not None:
            item.is_available = is_available
        if category_id is not None:
            item.category_id = category_id

        return self.repository.save(item)

    def _ensure_category_exists(self, category_id: int | None) -> None:
        if category_id is not None and not self.repository.get_category(category_id):
            raise NotFoundError("Категория не найдена")
