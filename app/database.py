"""
Модуль инициализации подключения к СУБД PostgreSQL.
"""
import functools

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL)
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
