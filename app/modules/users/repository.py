"""
Инфраструктурный слой модуля пользователей (круг 3: Interface Adapters).
"""
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.domain.entities import User
from app.models import User as UserModel


class UserRepository(ABC):
    """Контракт хранилища, от которого зависит UserService."""

    @abstractmethod
    def get_by_id(self, user_id: int) -> User | None: ...

    @abstractmethod
    def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    def create(self, email: str, phone: str | None) -> User:
        """Создаёт пользователя с нулевым балансом."""

    @abstractmethod
    def update_balance(self, user_id: int, new_balance: float) -> User: ...


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: int) -> User | None:
        user = self.db.query(UserModel).filter(UserModel.id == user_id).first()
        return user.to_entity() if user else None

    def get_by_email(self, email: str) -> User | None:
        user = self.db.query(UserModel).filter(UserModel.email == email).first()
        return user.to_entity() if user else None

    def create(self, email: str, phone: str | None) -> User:
        new_user = UserModel(email=email, phone=phone, balance=0.0, is_blocked=False)
        self.db.add(new_user)
        self.db.commit()
        self.db.refresh(new_user)
        return new_user.to_entity()

    def update_balance(self, user_id: int, new_balance: float) -> User:
        user = self.db.query(UserModel).filter(UserModel.id == user_id).one()
        user.balance = new_balance
        self.db.commit()
        self.db.refresh(user)
        return user.to_entity()
