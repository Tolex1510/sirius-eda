"""
Корень композиции: единственное место, где выбирается реализация репозиториев.
Сервисы и роутеры зависят только от абстракций, поэтому замена хранилища
(REPOSITORY_BACKEND=postgres|memory) не требует их изменения.
"""
import logging
from collections.abc import Iterator

from app.core.cache import CacheAside
from app.core.config import settings
from app.core.redis import get_redis
from app.database import SessionLocal
from app.memory_storage import InMemoryStorage
from app.modules.auth.repository import AuthRepository, InMemoryAuthRepository, SqlAlchemyAuthRepository
from app.modules.delivery.repository import (
    DeliveryRepository,
    InMemoryDeliveryRepository,
    SqlAlchemyDeliveryRepository,
)
from app.modules.menu.repository import (
    CachedMenuRepository,
    InMemoryMenuRepository,
    MenuRepository,
    SqlAlchemyMenuRepository,
)
from app.modules.orders.repository import InMemoryOrderRepository, OrderRepository, SqlAlchemyOrderRepository
from app.modules.users.repository import InMemoryUserRepository, SqlAlchemyUserRepository, UserRepository

logger = logging.getLogger(__name__)

memory_storage = InMemoryStorage()


def _provide(sql_repository_cls, memory_repository_cls) -> Iterator:
    if settings.REPOSITORY_BACKEND == "memory":
        yield memory_repository_cls(memory_storage)
        return

    db = SessionLocal()
    try:
        yield sql_repository_cls(db)
    finally:
        db.close()


def get_user_repository() -> Iterator[UserRepository]:
    yield from _provide(SqlAlchemyUserRepository, InMemoryUserRepository)


def _sql_menu_repository(db) -> MenuRepository:
    repository = SqlAlchemyMenuRepository(db)
    if settings.MENU_CACHE_ENABLED:
        return CachedMenuRepository(repository, CacheAside(get_redis()))
    return repository


def get_menu_repository() -> Iterator[MenuRepository]:
    yield from _provide(_sql_menu_repository, InMemoryMenuRepository)


def warm_up_menu_cache() -> None:
    """Вызывается при старте приложения. Ошибка прогрева не мешает запуску: кеш заполнится на первых запросах."""
    if settings.REPOSITORY_BACKEND != "postgres" or not settings.MENU_CACHE_ENABLED:
        return
    provider = get_menu_repository()
    try:
        repository = next(provider)
        repository.warm_up()
        logger.info("Menu cache warmed up")
    except Exception:
        logger.warning("Menu cache warm-up failed", exc_info=True)
    finally:
        provider.close()


def get_order_repository() -> Iterator[OrderRepository]:
    yield from _provide(SqlAlchemyOrderRepository, InMemoryOrderRepository)


def get_delivery_repository() -> Iterator[DeliveryRepository]:
    yield from _provide(SqlAlchemyDeliveryRepository, InMemoryDeliveryRepository)


def get_auth_repository() -> Iterator[AuthRepository]:
    yield from _provide(SqlAlchemyAuthRepository, InMemoryAuthRepository)
