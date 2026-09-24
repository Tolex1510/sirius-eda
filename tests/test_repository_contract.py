"""
Принцип подстановки Лисков: один и тот же сценарий OrderService
даёт одинаковый результат на любой реализации репозиториев.
SQLAlchemy-реализация проверяется на SQLite в памяти, запуск PostgreSQL не нужен.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.domain.exceptions import BusinessRuleError
from app.memory_storage import InMemoryStorage
from app.modules.menu.repository import InMemoryMenuRepository, SqlAlchemyMenuRepository
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
    try:
        yield SqlAlchemyUserRepository(db), SqlAlchemyMenuRepository(db), SqlAlchemyOrderRepository(db)
    finally:
        db.close()


@pytest.fixture(params=[memory_repositories, sqlalchemy_repositories], ids=["memory", "sqlalchemy"])
def repositories(request):
    yield from request.param()


def test_order_scenario_is_the_same_for_every_backend(repositories):
    user_repository, menu_repository, order_repository = repositories
    users = UserService(user_repository)
    menu = MenuService(menu_repository)
    orders = OrderService(order_repository)

    user = users.register("student@sirius.ru", None)
    users.top_up_balance(user.id, 500)
    item = menu.create_item("Плов", 150)

    order_id = orders.create_order(user.id, item.id, quantity=3)

    assert isinstance(order_id, int)
    assert user_repository.get_by_id(user.id).balance == 50

    with pytest.raises(BusinessRuleError):
        orders.create_order(user.id, item.id, quantity=1)
    assert user_repository.get_by_id(user.id).balance == 50
