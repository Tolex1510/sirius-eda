"""
Корень композиции: единственное место, где выбирается реализация репозиториев.
Сервисы и роутеры зависят только от абстракций, поэтому замена хранилища
(REPOSITORY_BACKEND=postgres|memory) не требует их изменения.
"""
from collections.abc import Iterator

from app.config import REPOSITORY_BACKEND
from app.database import SessionLocal
from app.memory_storage import InMemoryStorage
from app.modules.delivery.repository import (
    DeliveryRepository,
    InMemoryDeliveryRepository,
    SqlAlchemyDeliveryRepository,
)
from app.modules.menu.repository import InMemoryMenuRepository, MenuRepository, SqlAlchemyMenuRepository
from app.modules.orders.repository import InMemoryOrderRepository, OrderRepository, SqlAlchemyOrderRepository
from app.modules.users.repository import InMemoryUserRepository, SqlAlchemyUserRepository, UserRepository

memory_storage = InMemoryStorage()


def _provide(sql_repository_cls, memory_repository_cls) -> Iterator:
    if REPOSITORY_BACKEND == "memory":
        yield memory_repository_cls(memory_storage)
        return

    db = SessionLocal()
    try:
        yield sql_repository_cls(db)
    finally:
        db.close()


def get_user_repository() -> Iterator[UserRepository]:
    yield from _provide(SqlAlchemyUserRepository, InMemoryUserRepository)


def get_menu_repository() -> Iterator[MenuRepository]:
    yield from _provide(SqlAlchemyMenuRepository, InMemoryMenuRepository)


def get_order_repository() -> Iterator[OrderRepository]:
    yield from _provide(SqlAlchemyOrderRepository, InMemoryOrderRepository)


def get_delivery_repository() -> Iterator[DeliveryRepository]:
    yield from _provide(SqlAlchemyDeliveryRepository, InMemoryDeliveryRepository)

