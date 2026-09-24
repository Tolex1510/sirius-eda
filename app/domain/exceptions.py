"""
Исключения бизнес-логики. Наследуются от ValueError, как в шаблоне
лабораторной работы, но разделены по смыслу, чтобы транспортный слой
мог вернуть те же HTTP-статусы, что и MVP-версия (404, 403, 400).
"""


class DomainError(ValueError):
    pass


class NotFoundError(DomainError):
    pass


class AccessDeniedError(DomainError):
    pass


class BusinessRuleError(DomainError):
    pass
