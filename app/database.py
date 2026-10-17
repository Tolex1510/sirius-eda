"""
Модуль инициализации подключения к СУБД PostgreSQL.
"""
import functools

from sqlalchemy import URL, create_engine, make_url
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings


def database_url() -> URL:
    # В SQLAlchemy 2.1 драйвер по умолчанию для postgresql:// сменился с psycopg2 на psycopg 3.
    # В зависимостях psycopg2, поэтому без явного драйвера свежая установка не запустится.
    url = make_url(settings.DATABASE_URL)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg2")
    return url


engine = create_engine(database_url())
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Генератор сессии базы данных для использования в Depends."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def short_transactions(cls):
    """
    Каждый публичный метод SQL-репозитория завершает транзакцию и возвращает
    соединение в пул. Иначе сессия держит соединение до конца запроса, пока FastAPI
    сериализует ответ в пуле потоков. Под нагрузкой все потоки ждут соединение,
    а соединения ждут поток для сериализации: через 30 секунд QueuePool TimeoutError.

    Методы записи сами делают commit, для них откат ниже ничего не делает.
    Публичный метод не должен вызывать другой публичный метод между add() и commit():
    откат во вложенном вызове отменит незавершённую запись.
    """
    for name, method in list(vars(cls).items()):
        if callable(method) and not name.startswith("_"):
            setattr(cls, name, _release_connection_after(method))
    return cls


def _release_connection_after(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        finally:
            if self.db.in_transaction():
                self.db.rollback()
    return wrapper
