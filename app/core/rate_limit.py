"""
Ограничение частоты запросов на Redis. Счётчик общий для всех реплик приложения,
в отличие от счётчика в памяти процесса.
"""
import logging

from fastapi import Depends, HTTPException, Request
from redis import Redis, RedisError

from app.core.redis import get_redis

logger = logging.getLogger(__name__)


def rate_limit(max_requests: int, window_seconds: int, scope: str | None = None):
    """
    Фиксированное окно: не больше max_requests за window_seconds с одного IP.
    scope объединяет несколько эндпоинтов в один счётчик, например /auth/login и /auth/token.
    """
    def checker(request: Request, redis: Redis = Depends(get_redis)) -> None:
        key = f"rate_limit:{scope or request.url.path}:{request.client.host}"
        try:
            pipe = redis.pipeline()
            pipe.incr(key)
            # nx: окно не продлевается каждым запросом, иначе при постоянном потоке оно не закончится.
            pipe.expire(key, window_seconds, nx=True)
            pipe.ttl(key)
            current, _, ttl = pipe.execute()
        except RedisError:
            # Недоступность Redis не должна класть вход в систему. Отказ пишется в лог.
            logger.warning("Rate limiter unavailable, request allowed", exc_info=True)
            return

        if current > max_requests:
            raise HTTPException(
                status_code=429,
                detail="Слишком много запросов. Попробуйте позже",
                headers={"Retry-After": str(max(ttl, 1))},
            )
    return checker
