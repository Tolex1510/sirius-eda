import pytest

from app.domain.exceptions import BusinessRuleError, NotFoundError
from app.modules.menu.repository import InMemoryMenuRepository
from app.modules.menu.service import MenuService


@pytest.fixture
def service(storage) -> MenuService:
    return MenuService(InMemoryMenuRepository(storage))


def test_create_item_is_available(service):
    item = service.create_item("Борщ", 150)

    assert item.is_available is True


def test_create_item_rejects_duplicate_name(service):
    service.create_item("Борщ", 150)

    with pytest.raises(BusinessRuleError, match="уже существует"):
        service.create_item("Борщ", 200)


def test_update_changes_only_passed_fields(service, storage):
    item = service.create_item("Борщ", 150)

    service.update_item(item.id, price=180)

    saved = storage.menu_items[item.id]
    assert (saved.name, saved.price, saved.is_available) == ("Борщ", 180, True)


def test_update_unknown_item(service):
    with pytest.raises(NotFoundError, match="Блюдо не найдено"):
        service.update_item(999, name="Щи")
