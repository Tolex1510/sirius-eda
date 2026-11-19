"""
Cache-Aside поверх Redis с защитой от cache stampede.
Используется только инфраструктурным слоем (репозиториями): сервисы о кеше не знают.
"""
import json
import logging
import random
import time
from collections.abc import Callable
from typing import Any

from redis import Redis, RedisError
from redis.exceptions import LockError
from app.core.observability import cache_operations

logger = logging.getLogger(__name__)


class CacheAside:
    """
    get_or_load: hit отдаёт данные из Redis, miss загружает их из БД и кладёт в Redis.

    Stampede: когда ключ истёк под нагрузкой, в БД идёт только тот запрос, который
    взял блокировку lock:<ключ>. Остальные ждут, пока ключ появится, и читают его из кеша.
    Если Redis недоступен, данные берутся напрямую из БД: кеш ускоряет, но не нужен для работы.
    """

    def __init__(
        self,
        redis: Redis,
        lock_timeout: float = 5.0,
        wait_timeout: float = 3.0,
        poll_interval: float = 0.02,
        ttl_jitter: float = 0.1,
    ):
        self.redis = redis
        # Блокировка снимется сама, если её владелец упадёт посреди загрузки.
        self.lock_timeout = lock_timeout
        self.wait_timeout = wait_timeout
        self.poll_interval = poll_interval
        # Случайная добавка к TTL: ключи, записанные одновременно, не истекут одновременно.
        self.ttl_jitter = ttl_jitter

    def get_or_load(self, key: str, ttl: int, load: Callable[[], Any]) -> Any:
        """load возвращает JSON-совместимые данные: dict, list, числа, строки."""
        try:
            cached = self.redis.get(key)
            if cached is not None:
                cache_operations.labels(result="hit").inc()
                return json.loads(cached)
            cache_operations.labels(result="miss").inc()
            return self._load_once(key, ttl, load)
        except RedisError:
            cache_operations.labels(result="error").inc()
            logger.warning("Redis unavailable, reading %s from database", key, exc_info=True)
            return load()

    def put(self, key: str, ttl: int, value: Any) -> None:
        jitter = random.randint(0, int(ttl * self.ttl_jitter))
        self.redis.set(key, json.dumps(value, ensure_ascii=False), ex=ttl + jitter)

    def invalidate(self, *keys: str) -> None:
        try:
            self.redis.delete(*keys)
        except RedisError:
            # Запись в БД уже прошла. Устаревший кеш доживёт до TTL, это ограничивает вред.
            logger.warning("Failed to invalidate %s", keys, exc_info=True)

    def _load_once(self, key: str, ttl: int, load: Callable[[], Any]) -> Any:
        lock = self.redis.lock(f"lock:{key}", timeout=self.lock_timeout)
        if lock.acquire(blocking=False):
            try:
                # Пока брали блокировку, предыдущий владелец мог успеть заполнить кеш.
                cached = self.redis.get(key)
                if cached is not None:
                    return json.loads(cached)
                value = load()
                self.put(key, ttl, value)
                return value
            finally:
                try:
                    lock.release()
                except LockError:
                    # Загрузка заняла дольше lock_timeout, блокировка уже истекла.
                    pass

        deadline = time.monotonic() + self.wait_timeout
        while time.monotonic() < deadline:
            time.sleep(self.poll_interval)
            cached = self.redis.get(key)
            if cached is not None:
                return json.loads(cached)

        # Владелец блокировки не успел: лучше один лишний запрос в БД, чем бесконечное ожидание.
        logger.warning("Timed out waiting for %s, reading from database", key)
        return load()
