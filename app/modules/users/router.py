"""
Транспортный слой модуля пользователей (круг 4: Frameworks & Drivers).
"""
from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_current_user, require_role
from app.core.rate_limit import rate_limit
from app.core.security import MAX_PASSWORD_BYTES
from app.dependencies import get_user_repository
from app.domain.entities import Role, User
from app.domain.exceptions import DomainError
from app.http_errors import to_http_exception
from app.modules.users.repository import UserRepository
from app.modules.users.service import UserService
from app.schemas import RoleUpdate, UserCreate, UserResponse

router = APIRouter()


def get_user_service(repository: UserRepository = Depends(get_user_repository)) -> UserService:
    """Сборка слоёв: конкретный репозиторий внедряется в сервис через конструктор."""
    return UserService(repository)


@router.post("/register", dependencies=[Depends(rate_limit(5, 60))])
def register_user(payload: UserCreate, service: UserService = Depends(get_user_service)):
    # Формат email проверяет Pydantic (EmailStr), длину телефона проверяем здесь:
    # это техническая валидация, а уникальность email относится к бизнес-правилам сервиса.
    if payload.phone and len(payload.phone) < 10:
        raise HTTPException(
            status_code=400,
            detail="Некорректный формат номера телефона",
        )

    if len(payload.password.encode()) > MAX_PASSWORD_BYTES:
        raise HTTPException(
            status_code=400,
            detail="Пароль длиннее 72 байт",
        )

    try:
        user = service.register(email=payload.email, password=payload.password, phone=payload.phone)
    except DomainError as e:
        raise to_http_exception(e)

    return {
        "status": "success",
        "user_id": user.id,
        "email": user.email,
    }


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    try:
        return service.get_profile(user_id, actor=current_user)
    except DomainError as e:
        raise to_http_exception(e)


@router.post("/{user_id}/topup")
def top_up_balance(
    user_id: int,
    amount: float,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    if amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Сумма пополнения должна быть положительной",
        )

    try:
        new_balance = service.top_up_balance(user_id=user_id, amount=amount, actor=current_user)
    except DomainError as e:
        raise to_http_exception(e)

    return {"status": "success", "new_balance": new_balance}


@router.patch("/{user_id}/role", response_model=UserResponse)
def change_role(
    user_id: int,
    payload: RoleUpdate,
    _: User = Depends(require_role(Role.ADMIN)),
    service: UserService = Depends(get_user_service),
):
    try:
        return service.change_role(user_id, payload.role)
    except DomainError as e:
        raise to_http_exception(e)
