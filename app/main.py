"""
Точка входа приложения. Инициализирует FastAPI и подключает модули.
Схему БД создаёт и меняет Alembic: alembic upgrade head.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.modules.auth.router import router as auth_router
from app.modules.delivery.router import router as delivery_router
from app.modules.menu.router import router as menu_router
from app.modules.orders.router import kitchen_router
from app.modules.orders.router import router as orders_router
from app.modules.users.router import router as users_router

# Swagger раскрывает структуру API, поэтому в продакшене (DEBUG=false) он выключен.
app = FastAPI(
    title="Sirius.Food API",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(users_router, prefix="/users", tags=["users"])
app.include_router(menu_router, prefix="/menu", tags=["menu"])
app.include_router(orders_router, prefix="/orders", tags=["orders"])
app.include_router(kitchen_router, prefix="/kitchen", tags=["kitchen"])
app.include_router(delivery_router, prefix="/delivery", tags=["delivery"])
