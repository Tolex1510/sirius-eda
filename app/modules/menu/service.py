"""
Слой бизнес-логики модуля меню (круги 1 и 2: Entities и Use Cases).
Импорты fastapi и sqlalchemy здесь запрещены.
"""
from app.domain.entities import MenuItem
from app.domain.exceptions import BusinessRuleError, NotFoundError
from app.modules.menu.repository import MenuRepository


class MenuService:
    def __init__(self, repository: MenuRepository):
        self.repository = repository

    def create_item(self, name: str, price: float) -> MenuItem:
        if self.repository.get_by_name(name):
            raise BusinessRuleError("Блюдо с таким названием уже существует")
        return self.repository.create(name=name, price=price)

    def update_item(
        self,
        item_id: int,
        name: str | None = None,
        price: float | None = None,
        is_available: bool | None = None,
    ) -> MenuItem:
        item = self.repository.get_by_id(item_id)
        if not item:
            raise NotFoundError("Блюдо не найдено")

        if name is not None:
            item.name = name
        if price is not None:
            item.price = price
        if is_available is not None:
            item.is_available = is_available

        return self.repository.save(item)
