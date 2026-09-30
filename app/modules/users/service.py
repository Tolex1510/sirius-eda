"""
Слой бизнес-логики модуля пользователей (круги 1 и 2: Entities и Use Cases).
Импорты fastapi и sqlalchemy здесь запрещены.
"""
from app.core.security import hash_password
from app.domain.entities import Role, User
from app.domain.exceptions import AccessDeniedError, BusinessRuleError, NotFoundError
from app.modules.users.repository import UserRepository

MAX_TOP_UP_AMOUNT = 50000


class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    def register(
        self,
        email: str,
        password: str,
        phone: str | None = None,
        role: str = Role.STUDENT,
    ) -> User:
        if self.repository.get_by_email(email):
            raise BusinessRuleError("Пользователь с таким email уже зарегистрирован")
        return self.repository.create(
            email=email,
            phone=phone,
            password_hash=hash_password(password),
            role=role,
        )

    def get_profile(self, user_id: int, actor: User) -> User:
        return self._get_accessible(user_id, actor)

    def top_up_balance(self, user_id: int, amount: float, actor: User) -> float:
        """Пополняет баланс и возвращает новое значение."""
        user = self._get_accessible(user_id, actor)

        if user.is_blocked:
            raise AccessDeniedError("Пользователь заблокирован. Пополнение невозможно")

        if amount > MAX_TOP_UP_AMOUNT:
            raise BusinessRuleError("Максимальная сумма пополнения — 50000 рублей")

        updated = self.repository.update_balance(user_id, user.balance + amount)
        return updated.balance

    def change_role(self, user_id: int, role: str) -> User:
        if role not in Role.ALL:
            raise BusinessRuleError("Неизвестная роль")
        if not self.repository.get_by_id(user_id):
            raise NotFoundError("Пользователь не найден")
        return self.repository.set_role(user_id, role)

    def _get_accessible(self, user_id: int, actor: User) -> User:
        """Защита от IDOR: чужой аккаунт доступен только администратору."""
        if actor.id != user_id and actor.role != Role.ADMIN:
            raise AccessDeniedError("Нет доступа к чужому аккаунту")
        user = self.repository.get_by_id(user_id)
        if not user:
            raise NotFoundError("Пользователь не найден")
        return user
