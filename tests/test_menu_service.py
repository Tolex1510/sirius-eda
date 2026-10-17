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


def test_category_menu_contains_only_its_items(service):
    soups = service.create_category("Супы")
    salads = service.create_category("Салаты")
    service.create_item("Борщ", 150, category_id=soups.id)
    service.create_item("Цезарь", 250, category_id=salads.id)

    menu = service.get_category_menu(soups.id)

    assert (menu.id, menu.name, [i.name for i in menu.items]) == (soups.id, "Супы", ["Борщ"])


def test_unknown_category(service):
    with pytest.raises(NotFoundError, match="Категория не найдена"):
        service.get_category_menu(999)
    with pytest.raises(NotFoundError, match="Категория не найдена"):
        service.create_item("Борщ", 150, category_id=999)


def test_duplicate_category(service):
    service.create_category("Супы")

    with pytest.raises(BusinessRuleError, match="уже существует"):
        service.create_category("Супы")


def test_menu_is_sorted_by_category_then_name(service):
    soups = service.create_category("Супы")
    salads = service.create_category("Салаты")
    service.create_item("Щи", 120, category_id=soups.id)
    service.create_item("Без раздела", 50)
    service.create_item("Борщ", 150, category_id=soups.id)
    service.create_item("Цезарь", 250, category_id=salads.id)

    assert [i.name for i in service.list_items()] == ["Цезарь", "Борщ", "Щи", "Без раздела"]


def test_move_item_to_other_category(service):
    soups = service.create_category("Супы")
    hot = service.create_category("Горячее")
    item = service.create_item("Солянка", 180, category_id=soups.id)

    service.update_item(item.id, category_id=hot.id)

    assert service.get_category_menu(soups.id).items == []
    assert [i.name for i in service.get_category_menu(hot.id).items] == ["Солянка"]
