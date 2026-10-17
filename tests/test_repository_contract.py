"""
Принцип подстановки Лисков: один и тот же сценарий OrderService
даёт одинаковый результат на любой реализации репозиториев.
SQLAlchemy-реализация проверяется на SQLite в памяти, запуск PostgreSQL не нужен.
"""
import fakeredis
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.domain.entities import Role
from app.models import Role as RoleModel
from app.domain.exceptions import BusinessRuleError
from app.memory_storage import InMemoryStorage
from app.core.cache import CacheAside
from app.modules.menu.repository import CachedMenuRepository, InMemoryMenuRepository, SqlAlchemyMenuRepository
from app.modules.menu.service import MenuService
from app.modules.orders.repository import InMemoryOrderRepository, SqlAlchemyOrderRepository
from app.modules.orders.service import OrderService
from app.modules.users.repository import InMemoryUserRepository, SqlAlchemyUserRepository
from app.modules.users.service import UserService


def memory_repositories():
    storage = InMemoryStorage()
    yield InMemoryUserRepository(storage), InMemoryMenuRepository(storage), InMemoryOrderRepository(storage)


def sqlalchemy_repositories():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    # В PostgreSQL роли создаёт миграция 0002, здесь схема создана без Alembic.
    db.add_all(RoleModel(name=name) for name in Role.ALL)
    db.commit()
    try:
        yield SqlAlchemyUserRepository(db), SqlAlchemyMenuRepository(db), SqlAlchemyOrderRepository(db)
    finally:
        db.close()


def cached_sqlalchemy_repositories():
    for users, menu, orders in sqlalchemy_repositories():
        yield users, CachedMenuRepository(menu, CacheAside(fakeredis.FakeRedis(decode_responses=True))), orders


@pytest.fixture(
    params=[memory_repositories, sqlalchemy_repositories, cached_sqlalchemy_repositories],
    ids=["memory", "sqlalchemy", "sqlalchemy+redis"],
)
def repositories(request):
    yield from request.param()


def test_order_scenario_is_the_same_for_every_backend(repositories):
    user_repository, menu_repository, order_repository = repositories
    users = UserService(user_repository)
    menu = MenuService(menu_repository)
    orders = OrderService(order_repository)

    user = users.register("student@sirius.ru", "password123")
    users.top_up_balance(user.id, 500, actor=user)
    item = menu.create_item("Плов", 150)

    order_id = orders.create_order(user.id, item.id, quantity=3)

    assert isinstance(order_id, int)
    assert user_repository.get_by_id(user.id).balance == 50

    with pytest.raises(BusinessRuleError):
        orders.create_order(user.id, item.id, quantity=1)
    assert user_repository.get_by_id(user.id).balance == 50

    orders.cancel_order(order_id, actor=user)
    assert user_repository.get_by_id(user.id).balance == 500
    with pytest.raises(BusinessRuleError):
        orders.cancel_order(order_id, actor=user)
    assert user_repository.get_by_id(user.id).balance == 500
    assert user_repository.get_by_id(user.id).role == Role.STUDENT


def test_menu_categories_are_the_same_for_every_backend(repositories):
    _, menu_repository, _ = repositories
    menu = MenuService(menu_repository)
    soups = menu.create_category("Супы")
    salads = menu.create_category("Салаты")
    menu.create_item("Щи", 120, category_id=soups.id)
    menu.create_item("Без раздела", 50)
    menu.create_item("Борщ", 150, category_id=soups.id)
    menu.create_item("Цезарь", 250, category_id=salads.id)

    assert [i.name for i in menu.list_items()] == ["Цезарь", "Борщ", "Щи", "Без раздела"]
    assert [i.name for i in menu.get_category_menu(soups.id).items] == ["Борщ", "Щи"]
    assert [c.name for c in menu.list_categories()] == ["Салаты", "Супы"]
