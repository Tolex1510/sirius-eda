"""
Слой бизнес-логики модуля пользователей (круги 1 и 2: Entities и Use Cases).
Импорты fastapi и sqlalchemy здесь запрещены.
"""
from app.domain.entities import User
from app.domain.exceptions import AccessDeniedError, BusinessRuleError, NotFoundError
from app.modules.users.repository import UserRepository

MAX_TOP_UP_AMOUNT = 50000


class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    def register(self, email: str, phone: str | None) -> User:
        if self.repository.get_by_email(email):
            raise BusinessRuleError("Пользователь с таким email уже зарегистрирован")
        return self.repository.create(email=email, phone=phone)

    def top_up_balance(self, user_id: int, amount: float) -> float:
        """Пополняет баланс и возвращает новое значение."""
        user = self.repository.get_by_id(user_id)
        if not user:
            raise NotFoundError("Пользователь не найден")

        if user.is_blocked:
            raise AccessDeniedError("Пользователь заблокирован. Пополнение невозможно")

        if amount > MAX_TOP_UP_AMOUNT:
            raise BusinessRuleError("Максимальная сумма пополнения — 50000 рублей")

        updated = self.repository.update_balance(user_id, user.balance + amount)
        return updated.balance
