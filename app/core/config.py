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

    ACCESS_TOKEN_TTL_MINUTES: int = 15
    REFRESH_TOKEN_TTL_DAYS: int = 7
    # Стоимость bcrypt. 12 для продакшена, в тестах понижается ради скорости.
    BCRYPT_ROUNDS: int = Field(default=12, ge=4, le=16)

    # Вход через Google. Пока client id не задан, эндпоинты /auth/google/* отвечают 503.
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"


settings = Settings()
