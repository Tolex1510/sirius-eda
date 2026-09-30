"""
Исключения бизнес-логики. Наследуются от ValueError, как в шаблоне
лабораторной работы, но разделены по смыслу, чтобы транспортный слой
мог вернуть те же HTTP-статусы, что и MVP-версия (404, 403, 400).
"""


class DomainError(ValueError):
    pass


class AuthenticationError(DomainError):
    """Не удалось установить, кто делает запрос: неверный пароль или токен."""


class NotFoundError(DomainError):
    pass


class AccessDeniedError(DomainError):
    """Пользователь известен, но прав на действие или объект у него нет."""


class BusinessRuleError(DomainError):
    pass
