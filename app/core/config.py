"""
Настройки приложения. Читаются из переменных окружения и файла .env.
SECRET_KEY и DATABASE_URL обязательны: без них приложение не стартует.
"""
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SECRET_KEY: str = Field(min_length=32)
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"
    DEBUG: bool = False
    ALLOWED_ORIGINS: list[str] = []
    REPOSITORY_BACKEND: Literal["postgres", "memory"] = "postgres"
    # false выключает кеш меню: так снимается замер «до» без правки кода.
    MENU_CACHE_ENABLED: bool = True
    # sync выполняет PDF, email и SMS в потоке запроса: так снимается замер «до» без правки кода.
    ORDER_TASKS_MODE: Literal["celery", "sync"] = "celery"
    # Сбои заглушек внешних сервисов для показа ретраев и DLQ. 0 выключает сбой.
    FAKE_EMAIL_FAIL_EVERY: int = Field(default=5, ge=0)
    FAKE_SMS_FLAKY_EVERY: int = Field(default=3, ge=0)

    ACCESS_TOKEN_TTL_MINUTES: int = 15
    REFRESH_TOKEN_TTL_DAYS: int = 7
    # Стоимость bcrypt. 12 для продакшена, в тестах понижается ради скорости.
    BCRYPT_ROUNDS: int = Field(default=12, ge=4, le=16)

    # Вход через Google. Пока client id не задан, эндпоинты /auth/google/* отвечают 503.
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"


settings = Settings()
