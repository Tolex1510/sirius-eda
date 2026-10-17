"""
Общий клиент Redis: кеш меню и rate limiting.
decode_responses=True: из Redis приходят строки, а не байты, это удобно для JSON.
"""
import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from app.core.config import settings


def create_redis(url: str) -> redis.Redis:
    # Для кеша Redis необязателен: при сбое запрос должен сразу уйти в БД.
    # Повторы redis-py по умолчанию растянули бы каждый такой запрос на секунды.
    return redis.from_url(
        url,
        decode_responses=True,
        socket_timeout=0.5,
        socket_connect_timeout=0.5,
        retry=Retry(NoBackoff(), 0),
    )


redis_client = create_redis(settings.REDIS_URL)


def get_redis() -> redis.Redis:
    return redis_client


def check_redis_connection() -> bool:
    try:
        return redis_client.ping()
    except redis.RedisError:
        return False
