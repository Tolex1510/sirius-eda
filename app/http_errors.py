"""
Трансляция исключений бизнес-логики в HTTP-ответы. Используется только роутерами.
"""
from fastapi import HTTPException

from app.domain.exceptions import AccessDeniedError, AuthenticationError, DomainError, NotFoundError

STATUS_BY_ERROR = {
    AuthenticationError: 401,
    NotFoundError: 404,
    AccessDeniedError: 403,
}


def to_http_exception(error: DomainError) -> HTTPException:
    status_code = next(
        (code for cls, code in STATUS_BY_ERROR.items() if isinstance(error, cls)),
        400,
    )
    # RFC 6750: ответ 401 для Bearer-схемы обязан содержать этот заголовок.
    headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None
    return HTTPException(status_code=status_code, detail=str(error), headers=headers)
