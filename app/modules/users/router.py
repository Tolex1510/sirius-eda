"""
Транспортный слой модуля пользователей (круг 4: Frameworks & Drivers).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.domain.exceptions import DomainError
from app.http_errors import to_http_exception
from app.modules.users.repository import SqlAlchemyUserRepository
from app.modules.users.service import UserService
from app.schemas import UserCreate

router = APIRouter()


@router.post("/register")
def register_user(payload: UserCreate, db: Session = Depends(get_db)):
    # Формат email проверяет Pydantic (EmailStr), длину телефона проверяем здесь:
    # это техническая валидация, а уникальность email относится к бизнес-правилам сервиса.
    if payload.phone and len(payload.phone) < 10:
        raise HTTPException(
            status_code=400,
            detail="Некорректный формат номера телефона",
        )

    service = UserService(SqlAlchemyUserRepository(db))

    try:
        user = service.register(email=payload.email, phone=payload.phone)
    except DomainError as e:
        raise to_http_exception(e)

    return {
        "status": "success",
        "user_id": user.id,
        "email": user.email,
    }


@router.post("/{user_id}/topup")
def top_up_balance(user_id: int, amount: float, db: Session = Depends(get_db)):
    if amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Сумма пополнения должна быть положительной",
        )

    service = UserService(SqlAlchemyUserRepository(db))

    try:
        new_balance = service.top_up_balance(user_id=user_id, amount=amount)
    except DomainError as e:
        raise to_http_exception(e)

    return {"status": "success", "new_balance": new_balance}
