"""
Pydantic-схемы для валидации входных и выходных данных.
"""
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    phone: str | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    phone: str | None
    balance: float
    role: str


class RoleUpdate(BaseModel):
    role: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MenuItemCreate(BaseModel):
    name: str
    price: float


class MenuItemUpdate(BaseModel):
    name: str | None = None
    price: float | None = None
    is_available: bool | None = None


class OrderCreate(BaseModel):
    # user_id не принимается от клиента: заказчик берётся из JWT.
    item_id: int
    quantity: int


class DeliveryAssign(BaseModel):
    order_id: int
    courier_id: int
