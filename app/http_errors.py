"""
Трансляция исключений бизнес-логики в HTTP-ответы. Используется только роутерами.
"""
from fastapi import HTTPException

from app.domain.exceptions import AccessDeniedError, DomainError, NotFoundError

STATUS_BY_ERROR = {
    NotFoundError: 404,
    AccessDeniedError: 403,
}


def to_http_exception(error: DomainError) -> HTTPException:
    return HTTPException(
        status_code=STATUS_BY_ERROR.get(type(error), 400),
        detail=str(error),
    )
