"""
Корень композиции: единственное место, где выбирается реализация репозиториев.
Сервисы и роутеры зависят только от абстракций, поэтому замена хранилища
(REPOSITORY_BACKEND=postgres|memory) не требует их изменения.
"""
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager

from app.core.cache import CacheAside
from app.core.config import settings
from app.core.redis import get_redis
from app.database import SessionLocal
from app.memory_storage import InMemoryStorage
from app.modules.auth.repository import AuthRepository, InMemoryAuthRepository, SqlAlchemyAuthRepository
from app.modules.delivery.gateway import DeliveryGateway, LocalDeliveryGateway
from app.modules.delivery.grpc_client import delivery_grpc_gateway
from app.modules.delivery.repository import (
    DeliveryRepository,
    InMemoryDeliveryRepository,
    SqlAlchemyDeliveryRepository,
)
from app.modules.delivery.service import DeliveryService
from app.modules.menu.repository import (
    CachedMenuRepository,
    InMemoryMenuRepository,
    MenuRepository,
    SqlAlchemyMenuRepository,
)
from app.modules.orders.notifier import CeleryOrderNotifier, InlineOrderNotifier, OrderNotifier
from app.modules.orders.repository import InMemoryOrderRepository, OrderRepository, SqlAlchemyOrderRepository
from app.modules.users.repository import InMemoryUserRepository, SqlAlchemyUserRepository, UserRepository

logger = logging.getLogger(__name__)

memory_storage = InMemoryStorage()


@contextmanager
def _repository_scope(sql_repository_factory, memory_repository_cls) -> Iterator:
    """Репозиторий с собственной сессией БД. Для CLI и прогрева кеша."""
    if settings.REPOSITORY_BACKEND == "memory":
        yield memory_repository_cls(memory_storage)
        return

    db = SessionLocal()
    try:
        yield sql_repository_factory(db)
    finally:
        db.close()


def _sql_menu_repository(db) -> MenuRepository:
    repository = SqlAlchemyMenuRepository(db)
    if settings.MENU_CACHE_ENABLED:
        return CachedMenuRepository(repository, CacheAside(get_redis()))
    return repository


def user_repository_scope():
    return _repository_scope(SqlAlchemyUserRepository, InMemoryUserRepository)


def menu_repository_scope():
    return _repository_scope(_sql_menu_repository, InMemoryMenuRepository)


# Зависимости объявлены async: код после yield (закрытие сессии) выполняется в event loop
# и не ждёт свободный поток. Соединение к этому моменту уже в пуле, см. short_transactions.


async def get_user_repository() -> AsyncIterator[UserRepository]:
    with user_repository_scope() as repository:
        yield repository


async def get_menu_repository() -> AsyncIterator[MenuRepository]:
    with menu_repository_scope() as repository:
        yield repository


async def get_order_repository() -> AsyncIterator[OrderRepository]:
    with order_repository_scope() as repository:
        yield repository


def order_repository_scope():
    return _repository_scope(SqlAlchemyOrderRepository, InMemoryOrderRepository)


def get_order_notifier() -> OrderNotifier:
    if settings.ORDER_TASKS_MODE == "sync":
        return InlineOrderNotifier()
    return CeleryOrderNotifier()


async def get_delivery_repository() -> AsyncIterator[DeliveryRepository]:
    with _repository_scope(SqlAlchemyDeliveryRepository, InMemoryDeliveryRepository) as repository:
        yield repository


async def get_delivery_gateway() -> AsyncIterator[DeliveryGateway]:
    """Strangler Fig: доставка в микросервисе, прежний код монолита остаётся запасным путём."""
    if settings.DELIVERY_BACKEND == "grpc":
        yield delivery_grpc_gateway()
        return
    with _repository_scope(SqlAlchemyDeliveryRepository, InMemoryDeliveryRepository) as repository:
        yield LocalDeliveryGateway(DeliveryService(repository))


async def get_auth_repository() -> AsyncIterator[AuthRepository]:
    with _repository_scope(SqlAlchemyAuthRepository, InMemoryAuthRepository) as repository:
        yield repository


def warm_up_menu_cache() -> None:
    """Вызывается при старте приложения. Ошибка прогрева не мешает запуску: кеш заполнится на первых запросах."""
    if settings.REPOSITORY_BACKEND != "postgres" or not settings.MENU_CACHE_ENABLED:
        return
    try:
        with menu_repository_scope() as repository:
            repository.warm_up()
        logger.info("Menu cache warmed up")
    except Exception:
        logger.warning("Menu cache warm-up failed", exc_info=True)
