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

    # Доставка: grpc ходит в микросервис, local выполняет старый код монолита.
    # local оставлен по паттерну Strangler Fig: откат без деплоя, если сервис подвёл.
    DELIVERY_BACKEND: Literal["grpc", "local"] = "grpc"
    DELIVERY_GRPC_TARGET: str = "localhost:50051"
    # Канал без TLS, поэтому по умолчанию сервис слушает только локальный интерфейс.
    DELIVERY_GRPC_BIND: str = "127.0.0.1:50051"
    # Сколько монолит ждёт ответа сервиса. Обычный вызов занимает миллисекунды.
    DELIVERY_GRPC_TIMEOUT: float = Field(default=2.0, gt=0)

    # Брокер событий. Публикует в него только релей outbox, запрос оплаты брокера не ждёт.
    RABBITMQ_URL: str = "amqp://sirius:sirius@localhost:5672/"

    PUBLIC_URL: str = "http://localhost:8080"
    PAYMENT_PROVIDER: Literal["demo", "yookassa"] = "demo"
    YOOKASSA_SHOP_ID: str = ""
    YOOKASSA_SECRET_KEY: str = ""
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_HOST_HEADER: str = ""
    OLLAMA_MODEL: str = "qwen2.5:3b-instruct-q5_K_M"
    OLLAMA_EMBED_MODEL: str = "bge-m3:latest"
    AI_TIMEOUT: float = Field(default=90, gt=0, le=180)

    # Observability: Jaeger/Sentry подключаются опционально и не блокируют локальную разработку.
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    SENTRY_DSN: str = ""

    ACCESS_TOKEN_TTL_MINUTES: int = 15
    REFRESH_TOKEN_TTL_DAYS: int = 7
    # Стоимость bcrypt. 12 для продакшена, в тестах понижается ради скорости.
    BCRYPT_ROUNDS: int = Field(default=12, ge=4, le=16)

    # Вход через Google. Пока client id не задан, эндпоинты /auth/google/* отвечают 503.
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"


settings = Settings()
