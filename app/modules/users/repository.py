"""
Инфраструктурный слой модуля пользователей (круг 3: Interface Adapters).
"""
from abc import ABC, abstractmethod
from dataclasses import replace

from sqlalchemy.orm import Session

from app.domain.entities import Role, User
from app.memory_storage import InMemoryStorage
from app.models import Role as RoleModel
from app.models import User as UserModel


class UserRepository(ABC):
    """Контракт хранилища, от которого зависят UserService и AuthService."""

    @abstractmethod
    def get_by_id(self, user_id: int) -> User | None: ...

    @abstractmethod
    def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    def create(
        self,
        email: str,
        phone: str | None,
        password_hash: str | None,
        role: str = Role.STUDENT,
    ) -> User:
        """Создаёт пользователя с нулевым балансом."""

    @abstractmethod
    def update_balance(self, user_id: int, new_balance: float) -> User: ...

    @abstractmethod
    def set_role(self, user_id: int, role: str) -> User: ...


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, db: Session):
        self.db = db

    def _role_id(self, role: str) -> int:
        return self.db.query(RoleModel.id).filter(RoleModel.name == role).one()[0]

    def get_by_id(self, user_id: int) -> User | None:
        user = self.db.query(UserModel).filter(UserModel.id == user_id).first()
        return user.to_entity() if user else None

    def get_by_email(self, email: str) -> User | None:
        user = self.db.query(UserModel).filter(UserModel.email == email).first()
        return user.to_entity() if user else None

    def create(
        self,
        email: str,
        phone: str | None,
        password_hash: str | None,
        role: str = Role.STUDENT,
    ) -> User:
        new_user = UserModel(
            email=email,
            phone=phone,
            balance=0.0,
            is_blocked=False,
            password_hash=password_hash,
            role_id=self._role_id(role),
        )
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

    def set_role(self, user_id: int, role: str) -> User:
        user = self.db.query(UserModel).filter(UserModel.id == user_id).one()
        user.role_id = self._role_id(role)
        self.db.commit()
        self.db.refresh(user)
        return user.to_entity()


class InMemoryUserRepository(UserRepository):
    """Хранит данные в памяти процесса. Используется в тестах и без СУБД."""

    def __init__(self, storage: InMemoryStorage):
        self.storage = storage

    def get_by_id(self, user_id: int) -> User | None:
        user = self.storage.users.get(user_id)
        return replace(user) if user else None

    def get_by_email(self, email: str) -> User | None:
        for user in self.storage.users.values():
            if user.email == email:
                return replace(user)
        return None

    def create(
        self,
        email: str,
        phone: str | None,
        password_hash: str | None,
        role: str = Role.STUDENT,
    ) -> User:
        user = User(
            id=self.storage.next_id("users"),
            email=email,
            phone=phone,
            balance=0.0,
            is_blocked=False,
            role=role,
            password_hash=password_hash,
        )
        self.storage.users[user.id] = user
        return replace(user)

    def update_balance(self, user_id: int, new_balance: float) -> User:
        user = self.storage.users[user_id]
        user.balance = new_balance
        return replace(user)

    def set_role(self, user_id: int, role: str) -> User:
        user = self.storage.users[user_id]
        user.role = role
        return replace(user)
