"""
Cache-Aside для меню. Redis подменён fakeredis, «база» это InMemoryMenuRepository
со счётчиком обращений: по нему видно, пошёл запрос в БД или в кеш.
"""
import threading
import time

import fakeredis
import pytest

from app.core.cache import CacheAside
from app.core.redis import create_redis
from app.modules.menu.repository import (
    MENU_ALL_KEY,
    CachedMenuRepository,
    InMemoryMenuRepository,
    category_key,
)
from app.modules.menu.service import MenuService


class CountingRepository(InMemoryMenuRepository):
    """Считает чтения, которые дошли до «базы». delay имитирует тяжёлый SQL."""

    def __init__(self, storage, delay: float = 0.0):
        super().__init__(storage)
        self.delay = delay
        self.reads = 0
        self._lock = threading.Lock()

    def _count(self):
        with self._lock:
            self.reads += 1
        time.sleep(self.delay)

    def list_all(self):
        self._count()
        return super().list_all()

    def get_category_menu(self, category_id):
        self._count()
        return super().get_category_menu(category_id)


@pytest.fixture
def redis():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def db(storage):
    return CountingRepository(storage)


@pytest.fixture
def repository(db, redis):
    return CachedMenuRepository(db, CacheAside(redis))


@pytest.fixture
def service(repository):
    return MenuService(repository)


@pytest.fixture
def menu(service):
    soups = service.create_category("Супы")
    salads = service.create_category("Салаты")
    service.create_item("Борщ", 150, category_id=soups.id)
    service.create_item("Цезарь", 250, category_id=salads.id)
    return soups, salads


def test_second_read_is_a_cache_hit(service, db, redis, menu):
    first = service.list_items()
    second = service.list_items()

    assert first == second
    assert db.reads == 1
    assert 300 <= redis.ttl(MENU_ALL_KEY) <= 330


def test_category_has_its_own_key_and_longer_ttl(service, db, redis, menu):
    soups, _ = menu

    service.get_category_menu(soups.id)
    service.get_category_menu(soups.id)

    assert db.reads == 1
    assert 600 <= redis.ttl(category_key(soups.id)) <= 660


def test_cached_data_matches_database(service, storage, menu):
    soups, _ = menu
    plain = MenuService(InMemoryMenuRepository(storage))

    service.list_items()
    service.get_category_menu(soups.id)

    assert service.list_items() == plain.list_items()
    assert service.get_category_menu(soups.id) == plain.get_category_menu(soups.id)


def test_new_item_is_visible_immediately(service, redis, menu):
    soups, _ = menu
    service.list_items()
    service.get_category_menu(soups.id)

    service.create_item("Щи", 120, category_id=soups.id)

    assert "Щи" in [i.name for i in service.list_items()]
    assert "Щи" in [i.name for i in service.get_category_menu(soups.id).items]


def test_update_drops_only_affected_keys(service, redis, menu):
    soups, salads = menu
    drinks = service.create_category("Напитки")
    service.list_items()
    for category in (soups, salads, drinks):
        service.get_category_menu(category.id)
    borsch = service.list_items()[1]

    service.update_item(borsch.id, price=170)

    assert not redis.exists(MENU_ALL_KEY)
    assert not redis.exists(category_key(soups.id))
    assert redis.exists(category_key(salads.id))
    assert service.get_category_menu(soups.id).items[0].price == 170


def test_moving_item_refreshes_both_categories(service, menu):
    soups, salads = menu
    service.get_category_menu(soups.id)
    service.get_category_menu(salads.id)
    borsch = next(i for i in service.list_items() if i.name == "Борщ")

    service.update_item(borsch.id, category_id=salads.id)

    assert service.get_category_menu(soups.id).items == []
    assert {i.name for i in service.get_category_menu(salads.id).items} == {"Борщ", "Цезарь"}


def test_missing_category_is_cached_until_it_is_created(service, db):
    assert service.repository.get_category_menu(1) is None
    assert service.repository.get_category_menu(1) is None
    assert db.reads == 1

    created = service.create_category("Супы")

    assert created.id == 1
    assert service.get_category_menu(1).name == "Супы"


def test_redis_outage_falls_back_to_database_quickly(db, menu):
    # Клиент с продовыми настройками, Redis на этом порту не слушает.
    down = CachedMenuRepository(db, CacheAside(create_redis("redis://127.0.0.1:1/0")))
    service = MenuService(down)

    started = time.monotonic()
    assert [i.name for i in service.list_items()] == ["Цезарь", "Борщ"]
    service.create_item("Щи", 120)
    assert len(service.list_items()) == 3
    assert time.monotonic() - started < 1


def test_stampede_sends_one_query_to_database(storage, redis, menu):
    slow_db = CountingRepository(storage, delay=0.3)
    repository = CachedMenuRepository(slow_db, CacheAside(redis))
    results = []
    start = threading.Barrier(20)

    def read():
        start.wait()
        results.append(repository.list_all())

    threads = [threading.Thread(target=read) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert slow_db.reads == 1
    assert len(results) == 20
    assert all(result == results[0] for result in results)


def test_waiters_fall_back_to_database_if_lock_holder_dies(db, redis, menu):
    redis.set(f"lock:{MENU_ALL_KEY}", "crashed-worker", px=5000)
    repository = CachedMenuRepository(db, CacheAside(redis, wait_timeout=0.1))

    assert [i.name for i in repository.list_all()] == ["Цезарь", "Борщ"]
    assert db.reads == 1


def test_lock_is_released_after_loading(repository, redis, menu):
    repository.list_all()

    assert not redis.exists(f"lock:{MENU_ALL_KEY}")


def test_warm_up_fills_every_key(repository, db, redis, menu):
    soups, salads = menu

    repository.warm_up()
    reads_after_warm_up = db.reads
    repository.list_all()
    repository.get_category_menu(soups.id)
    repository.get_category_menu(salads.id)

    assert redis.exists(MENU_ALL_KEY, category_key(soups.id), category_key(salads.id)) == 3
    assert db.reads == reads_after_warm_up


def test_ttl_jitter_spreads_expiry(redis):
    cache = CacheAside(redis)

    for i in range(30):
        cache.put(f"key:{i}", 300, i)

    ttls = {redis.ttl(f"key:{i}") for i in range(30)}
    assert len(ttls) > 1
    assert all(300 <= ttl <= 330 for ttl in ttls)
